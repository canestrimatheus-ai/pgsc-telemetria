import time
import functools
import hmac
import os
import io
import json
import sqlite3
from flask import Flask, render_template, jsonify, request, send_file, redirect, url_for, make_response, g
import database
import efetividade
import auth
import pandas as pd

WRITE_TOKEN = os.environ.get('TELEMETRIA_WRITE_TOKEN', '') or ''
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

class PrefixMiddleware:
    def __init__(self, wsgi_app, default_prefix='/telemetria'):
        self.wsgi_app = wsgi_app
        self.prefix = (os.environ.get('BASE_PATH', default_prefix) or '').rstrip('/')

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        if self.prefix:
            if path == self.prefix:
                start_response('301 Moved Permanently', [('Location', self.prefix + '/')])
                return [b'']
            if path.startswith(self.prefix + '/'):
                environ['PATH_INFO'] = path[len(self.prefix):] or '/'
                environ['SCRIPT_NAME'] = self.prefix
        return self.wsgi_app(environ, start_response)

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.wsgi_app = PrefixMiddleware(app.wsgi_app)

@app.context_processor
def inject_globals():
    return {
        'v': str(int(time.time())),
        'current_user': getattr(g, 'current_user', None)
    }

@app.after_request
def add_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# ── INICIALIZAÇÃO DE BANCO E ROOT ADMIN ──
database.init_db()
database.seed_db_from_excel()
auth.init_auth_db()

ROOT_ADMIN_EMAIL = 'matheuscamilio@expressonepomuceno.com.br'
def ensure_root_admin():
    try:
        user = auth.get_user_by_email(ROOT_ADMIN_EMAIL)
        if not user:
            user = auth.create_user(
                email=ROOT_ADMIN_EMAIL,
                nome='Matheus Camilio',
                role='MATRIZ',
                operacao=''
            )
            token = auth.create_auth_token(user['id'], tipo='setup_password', expires_minutes=120)
            try:
                auth.send_auth_email(ROOT_ADMIN_EMAIL, 'Matheus Camilio', token, tipo='setup_password')
                print(f"[AUTH] Usuário root criado e e-mail de ativação enviado para {ROOT_ADMIN_EMAIL}")
            except Exception as mail_err:
                print(f"[AUTH] Erro ao enviar e-mail de ativação root: {mail_err}")
    except Exception as e:
        print(f"[AUTH] Falha ao verificar/criar root admin: {e}")

ensure_root_admin()

# ── HELPER DE ESCOPO DE OPERAÇÃO (RBAC) ──
def get_effective_operacao():
    user = getattr(g, 'current_user', None) or {}
    role = (user.get('role') or '').upper()
    req_op = (request.args.get('operacao') or '').strip()

    if role == 'MATRIZ':
        return req_op

    # Para OPERACAO e TREINAMENTO:
    raw_user_op = user.get('operacao') or ''
    user_ops = [o.strip().upper() for o in raw_user_op.split(',') if o.strip()]
    if not user_ops:
        return '__NONE__'

    if req_op:
        req_list = [o.strip().upper() for o in req_op.split(',') if o.strip()]
        allowed = [o for o in req_list if o in user_ops]
        if allowed:
            return ','.join(allowed)

    return ','.join(user_ops)

def check_user_driver_permission(codigo):
    user = getattr(g, 'current_user', None) or {}
    role = (user.get('role') or '').upper()
    if role == 'MATRIZ':
        return True
    data = database.get_motorista_detail(codigo)
    if not data:
        return False
    mot = data.get('motorista') or data
    user_ops = [o.strip().upper() for o in (user.get('operacao') or '').split(',') if o.strip()]
    return (mot.get('operacao') or '').upper() in user_ops

# ══════════════════════════════════════════════════════════════
# ROTAS DE AUTENTICAÇÃO E SESSÃO
# ══════════════════════════════════════════════════════════════

@app.route('/login')
def login_view():
    current_user = auth.get_current_user()
    if current_user:
        return redirect(url_for('index'))
    
    error_code = request.args.get('error', '')
    error_msg = None
    if error_code == 'expired' or error_code == 'link_expirado':
        error_msg = 'O link de acesso expirou ou já foi utilizado. Solicite um novo link abaixo.'
    elif error_code == 'invalid_token':
        error_msg = 'Link de acesso inválido.'
    elif error_code == 'inactive':
        error_msg = 'Sua conta de usuário foi desativada pelo administrador.'

    return render_template('login.html', error_msg=error_msg)

@app.route('/auth/setup-password')
def setup_password_view():
    token = request.args.get('token', '').strip()
    if not token:
        return redirect(url_for('login_view', error='invalid_token'))
    
    conn = auth.get_db()
    c = conn.cursor()
    now_str = auth.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('''
    SELECT t.*, u.id as user_id, u.email, u.nome, u.role, u.operacao, u.ativo
    FROM auth_tokens t
    JOIN usuarios u ON t.user_id = u.id
    WHERE t.token = ? AND t.used = 0 AND t.expires_at > ?
    ''', (token, now_str))
    row = c.fetchone()
    conn.close()

    if not row:
        return redirect(url_for('login_view', error='link_expirado'))

    user = dict(row)
    return render_template('setup_password.html', token=token, user=user)

@app.route('/auth/verify')
def auth_verify():
    # Login exclusivo por senha. Redireciona para tela de login ou cadastro de senha se token fornecido.
    token = request.args.get('token', '').strip()
    if token:
        return redirect(url_for('setup_password_view', token=token))
    return redirect(url_for('login_view'))

@app.route('/auth/logout')
def logout_view():
    session_id = request.cookies.get('pgcsc_session')
    if session_id:
        auth.delete_session(session_id)
    resp = redirect(url_for('login_view'))
    resp.delete_cookie('pgcsc_session', path='/')
    return resp

@app.route('/api/auth/forgot-password', methods=['POST'])
def api_auth_forgot_password():
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({'error': 'Informe o e-mail corporativo.'}), 400

    user = auth.get_user_by_email(email)
    if not user:
        return jsonify({'error': 'E-mail não encontrado no sistema. Solicite seu cadastro à equipe da Matriz.'}), 404

    if not user.get('ativo', 1):
        return jsonify({'error': 'Usuário desativado. Entre em contato com a equipe da Matriz.'}), 403

    token = auth.create_auth_token(user['id'], tipo='setup_password', expires_minutes=120)
    try:
        auth.send_auth_email(user['email'], user['nome'], token, tipo='forgot_password')
    except Exception as e:
        return jsonify({'error': f'Erro ao transmitir e-mail: {str(e)}'}), 500

    return jsonify({
        'success': True,
        'message': f'Link seguro para cadastrar/redefinir sua senha foi enviado para {user["email"]}.'
    })

@app.route('/api/auth/login-password', methods=['POST'])
def api_auth_login_password():
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'E-mail e senha são obrigatórios.'}), 400

    user = auth.get_user_by_email(email)
    if not user:
        return jsonify({'error': 'Credenciais inválidas.'}), 401

    if not user.get('ativo', 1):
        return jsonify({'error': 'Usuário desativado pelo administrador.'}), 403

    if not user.get('password_hash'):
        return jsonify({'error': 'Você ainda não cadastrou uma senha. Clique em "Esqueci minha senha" para receber o link de cadastro no seu e-mail corporativo.'}), 400

    if not auth.verify_password(user['password_hash'], password):
        return jsonify({'error': 'E-mail ou senha incorretos.'}), 401

    session_id = auth.create_session(user['id'])
    resp = jsonify({
        'success': True,
        'message': 'Autenticado com sucesso!',
        'user': {
            'id': user['id'],
            'email': user['email'],
            'nome': user['nome'],
            'role': user['role'],
            'operacao': user['operacao']
        }
    })
    resp.set_cookie(
        'pgcsc_session',
        session_id,
        max_age=14 * 86400,
        httponly=True,
        samesite='Lax',
        path='/'
    )
    return resp

@app.route('/api/auth/setup-password', methods=['POST'])
def api_auth_setup_password():
    data = request.json or {}
    token = (data.get('token') or '').strip()
    password = data.get('password') or ''

    if not token or not password:
        return jsonify({'error': 'Token e senha são obrigatórios.'}), 400

    if len(password) < 6:
        return jsonify({'error': 'A senha deve conter no mínimo 6 caracteres.'}), 400

    user = auth.verify_and_consume_token(token)
    if not user:
        return jsonify({'error': 'Link expirado ou já utilizado.'}), 400

    auth.update_user_password(user['user_id'], password)
    session_id = auth.create_session(user['user_id'])

    resp = jsonify({
        'success': True,
        'message': 'Senha cadastrada com sucesso!'
    })
    resp.set_cookie(
        'pgcsc_session',
        session_id,
        max_age=14 * 86400,
        httponly=True,
        samesite='Lax',
        path='/'
    )
    return resp

@app.route('/api/auth/me')
@auth.login_required()
def api_auth_me():
    user = g.current_user
    return jsonify({
        'id': user['id'],
        'email': user['email'],
        'nome': user['nome'],
        'role': user['role'],
        'operacao': user['operacao']
    })

# ══════════════════════════════════════════════════════════════
# GESTÃO DE USUÁRIOS (APENAS MATRIZ)
# ══════════════════════════════════════════════════════════════

@app.route('/api/admin/usuarios', methods=['GET'])
@auth.login_required(allowed_roles=['MATRIZ'])
def api_admin_list_users():
    users = auth.list_users()
    return jsonify(users)

@app.route('/api/admin/usuarios', methods=['POST'])
@auth.login_required(allowed_roles=['MATRIZ'])
def api_admin_create_user():
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    nome = (data.get('nome') or '').strip()
    role = (data.get('role') or 'OPERACAO').strip().upper()
    operacao = data.get('operacao') or ''
    telefone = (data.get('telefone') or '').strip()

    if not email or not nome:
        return jsonify({'error': 'E-mail e Nome são obrigatórios.'}), 400

    existing = auth.get_user_by_email(email)
    if existing:
        return jsonify({'error': 'Já existe um usuário cadastrado com este e-mail.'}), 400

    if role not in ['MATRIZ', 'TREINAMENTO', 'OPERACAO']:
        return jsonify({'error': 'Perfil inválido.'}), 400

    if role in ['OPERACAO', 'TREINAMENTO']:
        if isinstance(operacao, (list, tuple)):
            ops = [str(o).strip().upper() for o in operacao if str(o).strip()]
        else:
            ops = [str(o).strip().upper() for o in str(operacao).split(',') if str(o).strip()]
        if not ops:
            return jsonify({'error': 'Selecione ao menos uma operação vinculada para este usuário.'}), 400
        operacao_clean = ', '.join(ops)
    else:
        operacao_clean = ''

    user = auth.create_user(email=email, nome=nome, role=role, operacao=operacao_clean, telefone=telefone)
    token = auth.create_auth_token(user['id'], tipo='setup_password', expires_minutes=120)

    email_sent = False
    try:
        auth.send_auth_email(email, nome, token, tipo='setup_password')
        email_sent = True
    except Exception as e:
        print(f"[AUTH] Falha ao enviar convite por e-mail para {email}: {e}")

    whatsapp_sent = False
    whatsapp_error = None
    if user.get('telefone'):
        try:
            auth.send_auth_whatsapp(user['telefone'], nome, token, tipo='setup_password')
            whatsapp_sent = True
        except Exception as e:
            whatsapp_error = str(e)
            print(f"[AUTH] Falha ao enviar WhatsApp para {user['telefone']}: {e}")

    messages = [f"Usuário {nome} cadastrado com sucesso!"]
    if email_sent:
        messages.append("E-mail enviado.")
    if whatsapp_sent:
        messages.append("WhatsApp disparado pelo robô.")
    elif whatsapp_error:
        messages.append(f"(Aviso WhatsApp: {whatsapp_error})")

    return jsonify({
        'success': True,
        'message': " ".join(messages),
        'user': user
    })

@app.route('/api/admin/usuarios/<int:user_id>', methods=['GET'])
@auth.login_required(allowed_roles=['MATRIZ'])
def api_admin_get_user(user_id):
    user = auth.get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'Usuário não encontrado.'}), 404
    # Do not expose password_hash
    user_dict = dict(user)
    user_dict.pop('password_hash', None)
    return jsonify(user_dict)

@app.route('/api/admin/usuarios/<int:user_id>', methods=['PUT', 'POST'])
@app.route('/api/admin/usuarios/<int:user_id>/editar', methods=['POST'])
@auth.login_required(allowed_roles=['MATRIZ'])
def api_admin_update_user(user_id):
    user = auth.get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'Usuário não encontrado.'}), 404

    data = request.json or {}
    nome = (data.get('nome') or '').strip()
    email = (data.get('email') or '').strip().lower()
    telefone = (data.get('telefone') or '').strip()
    role = (data.get('role') or user.get('role') or 'OPERACAO').strip().upper()
    operacao = data.get('operacao', '')
    nova_senha = (data.get('nova_senha') or '').strip()

    if not nome or not email:
        return jsonify({'error': 'Nome e E-mail são obrigatórios.'}), 400

    is_root = user['email'].lower() == ROOT_ADMIN_EMAIL.lower()
    if is_root:
        role = 'MATRIZ'

    if role not in ['MATRIZ', 'TREINAMENTO', 'OPERACAO']:
        return jsonify({'error': 'Perfil inválido.'}), 400

    if role in ['OPERACAO', 'TREINAMENTO']:
        if isinstance(operacao, (list, tuple)):
            ops = [str(o).strip().upper() for o in operacao if str(o).strip()]
        else:
            ops = [str(o).strip().upper() for o in str(operacao).split(',') if str(o).strip()]
        if not ops:
            return jsonify({'error': 'Selecione ao menos uma operação vinculada para este usuário.'}), 400
        operacao_clean = ', '.join(ops)
    else:
        operacao_clean = ''

    try:
        updated = auth.update_user(
            user_id=user_id,
            nome=nome,
            email=email,
            role=role,
            operacao=operacao_clean,
            telefone=telefone
        )
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400

    if nova_senha:
        if len(nova_senha) < 6:
            return jsonify({'error': 'A nova senha deve ter no mínimo 6 caracteres.'}), 400
        auth.update_user_password(user_id, nova_senha)

    return jsonify({
        'success': True,
        'message': f'Usuário {nome} atualizado com sucesso!',
        'user': updated
    })

@app.route('/api/admin/usuarios/<int:user_id>/update-phone', methods=['POST'])
@auth.login_required(allowed_roles=['MATRIZ'])
def api_admin_update_phone(user_id):
    user = auth.get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'Usuário não encontrado.'}), 404

    data = request.json or {}
    telefone = data.get('telefone', '')
    updated_user = auth.update_user_phone(user_id, telefone)
    return jsonify({
        'success': True,
        'message': 'Telefone atualizado com sucesso!',
        'user': updated_user
    })

@app.route('/api/admin/usuarios/<int:user_id>/send-whatsapp', methods=['POST'])
@auth.login_required(allowed_roles=['MATRIZ'])
def api_admin_send_whatsapp(user_id):
    user = auth.get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'Usuário não encontrado.'}), 404

    data = request.json or {}
    if 'telefone' in data:
        telefone = data.get('telefone', '')
        user = auth.update_user_phone(user_id, telefone)

    phone = user.get('telefone')
    if not phone:
        return jsonify({'error': 'Usuário não possui número de telefone cadastrado.'}), 400

    token = auth.create_auth_token(user['id'], tipo='setup_password', expires_minutes=120)

    try:
        res = auth.send_auth_whatsapp(phone, user['nome'], token, tipo='setup_password')
        return jsonify({
            'success': True,
            'message': 'Convite enviado com sucesso via WhatsApp!',
            'whatsappUrl': res.get('whatsapp_web_url')
        })
    except Exception as e:
        import urllib.parse
        base_clean = 'https://decamservice.com/telemetria'
        action_url = f"{base_clean}/auth/setup-password?token={token}"
        primeiro_nome = (user.get('nome') or 'Colega').strip().split()[0]
        msg = (
            f"Olá, *{primeiro_nome}*! 👋\n\n"
            f"Você foi cadastrado na plataforma *PGCSC Telemetria* da *Expresso Nepomuceno*!\n\n"
            f"Para cadastrar sua senha de acesso com segurança, clique no link abaixo:\n\n"
            f"{action_url}\n\n"
            f"⏱️ _Link válido por 2 horas._\n\n"
            f"💡 _Se o link acima não estiver clicável, responda esta mensagem com um *OK* para liberar o link no WhatsApp._"
        )
        clean_phone = auth.normalize_phone(phone)
        fallback_web = f"https://wa.me/{clean_phone}?text={urllib.parse.quote(msg)}" if clean_phone else None
        return jsonify({
            'error': f'Falha ao disparar pelo robô: {str(e)}',
            'whatsappUrl': fallback_web
        }), 500

@app.route('/api/admin/usuarios/<int:user_id>/toggle-status', methods=['POST'])
@auth.login_required(allowed_roles=['MATRIZ'])
def api_admin_toggle_user_status(user_id):
    user = auth.get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'Usuário não encontrado.'}), 404

    if user['email'].lower() == ROOT_ADMIN_EMAIL.lower():
        return jsonify({'error': 'Não é permitido desativar o usuário Administrador Root.'}), 403

    novo_status = 0 if user['ativo'] else 1
    auth.update_user_status(user_id, novo_status)
    return jsonify({
        'success': True,
        'message': f'Usuário {"ativado" if novo_status else "desativado"} com sucesso!'
    })

@app.route('/api/admin/usuarios/<int:user_id>/resend-invite', methods=['POST'])
@auth.login_required(allowed_roles=['MATRIZ'])
def api_admin_resend_invite(user_id):
    user = auth.get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'Usuário não encontrado.'}), 404

    token = auth.create_auth_token(user['id'], tipo='setup_password', expires_minutes=120)

    try:
        auth.send_auth_email(user['email'], user['nome'], token, tipo='setup_password')
    except Exception as e:
        return jsonify({'error': f'Erro ao enviar e-mail: {str(e)}'}), 500

    return jsonify({
        'success': True,
        'message': f'Link para cadastro/redefinição de senha enviado para {user["email"]}!'
    })

@app.route('/api/admin/usuarios/<int:user_id>', methods=['DELETE'])
@auth.login_required(allowed_roles=['MATRIZ'])
def api_admin_delete_user(user_id):
    user = auth.get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'Usuário não encontrado.'}), 404

    if user['email'].lower() == ROOT_ADMIN_EMAIL.lower():
        return jsonify({'error': 'Não é permitido excluir o usuário Administrador Root.'}), 403

    auth.delete_user(user_id)
    return jsonify({'success': True, 'message': 'Usuário excluído com sucesso!'})

@app.route('/api/admin/operacoes-lista')
@auth.login_required()
def api_admin_operacoes_lista():
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT operacao FROM motoristas WHERE operacao IS NOT NULL AND TRIM(operacao) != ''
        UNION
        SELECT DISTINCT operacao FROM reciclagens WHERE operacao IS NOT NULL AND TRIM(operacao) != ''
        ORDER BY operacao ASC
    """)
    ops = [r[0] for r in c.fetchall() if r[0]]
    conn.close()
    return jsonify(ops)

# ══════════════════════════════════════════════════════════════
# ROTAS PRINCIPAIS PROTEGIDAS (COM RBAC & ESCOPO DE OPERAÇÃO)
# ══════════════════════════════════════════════════════════════

@app.route('/')
@auth.login_required()
def index():
    return render_template('index.html', user=g.current_user)

@app.route('/guia')
@auth.login_required()
def guia():
    return render_template('guia_funcional.html', user=g.current_user)

@app.route('/api/kpis')
@auth.login_required()
def api_kpis():
    operacao = get_effective_operacao()
    ano = request.args.get('ano', '')
    mes = request.args.get('mes', '')
    data = database.get_kpis_data(operacao=operacao, ano=ano, mes=mes)
    return jsonify(data)

@app.route('/api/kanban')
@auth.login_required()
def api_kanban():
    operacao = get_effective_operacao()
    gestor = request.args.get('gestor', '')
    search = request.args.get('search', '')
    mes = request.args.get('mes', '')
    ano = request.args.get('ano', '')
    data = database.get_kanban_data(operacao=operacao, gestor=gestor, search=search, mes=mes, ano=ano)
    return jsonify(data)

@app.route('/api/alertas')
@auth.login_required()
def api_alertas():
    data = database.get_automatic_alerts()
    user_op = get_effective_operacao()
    if user_op and user_op != '__NONE__':
        allowed_ops = [o.strip().upper() for o in user_op.split(',') if o.strip()]
        data = [a for a in data if (a.get('operacao') or '').upper() in allowed_ops]
    elif user_op == '__NONE__':
        data = []
    return jsonify(data)

@app.route('/api/faixas-risco')
@auth.login_required()
def api_faixas_risco():
    operacao = get_effective_operacao()
    ano = request.args.get('ano', '')
    mes = request.args.get('mes', '')
    data = database.get_faixas_risco_data(operacao=operacao, ano=ano, mes=mes)
    return jsonify(data)

@app.route('/api/comparativo-mensal')
@auth.login_required()
def api_comparativo_mensal():
    operacao = get_effective_operacao()
    ano = request.args.get('ano', '')
    mes = request.args.get('mes', '')
    data = database.get_comparativo_mensal_data(operacao=operacao, ano=ano, mes=mes)
    return jsonify(data)

@app.route('/api/ia-relatorio-comparativo')
@auth.login_required()
def api_ia_relatorio_comparativo():
    operacao = get_effective_operacao()
    ano = request.args.get('ano', '')
    mes = request.args.get('mes', '')
    data = database.gerar_relatorio_ia_comparativo(operacao=operacao, ano=ano, mes=mes)
    return jsonify(data)

@app.route('/api/ranking-operacoes')
@auth.login_required()
def api_ranking_operacoes():
    user = g.current_user
    ano = request.args.get('ano', '')
    mes = request.args.get('mes', '')
    data = database.get_ranking_operacoes_data(ano=ano, mes=mes)
    role = (user.get('role') or '').upper()
    if role in ['OPERACAO', 'TREINAMENTO']:
        user_ops = [o.strip().upper() for o in (user.get('operacao') or '').split(',') if o.strip()]
        data = [d for d in data if (d.get('operacao') or '').upper() in user_ops]
    return jsonify(data)

@app.route('/api/ranking-gestores')
@auth.login_required()
def api_ranking_gestores():
    data = database.get_ranking_gestores_data()
    user = g.current_user
    role = (user.get('role') or '').upper()
    if role in ['OPERACAO', 'TREINAMENTO']:
        user_ops = [o.strip().upper() for o in (user.get('operacao') or '').split(',') if o.strip()]
        if not user_ops:
            return jsonify([])
        conn = database.get_db_connection()
        c = conn.cursor()
        ph = ','.join(['?'] * len(user_ops))
        c.execute(f"SELECT DISTINCT gestor FROM motoristas WHERE operacao IN ({ph})", user_ops)
        allowed_gestores = set(r[0] for r in c.fetchall() if r[0])
        conn.close()
        data = [d for d in data if d.get('gestor') in allowed_gestores]
    return jsonify(data)

@app.route('/api/anos-disponiveis')
@auth.login_required()
def api_anos_disponiveis():
    data = database.get_anos_disponiveis()
    return jsonify(data)

@app.route('/api/top-motoristas-excessos')
@auth.login_required()
def api_top_motoristas_excessos():
    operacao = get_effective_operacao()
    ano = request.args.get('ano', '')
    mes = request.args.get('mes', '')
    limit = int(request.args.get('limit', 10))
    data = database.get_top_motoristas_excessos(operacao=operacao, limit=limit, ano=ano, mes=mes)
    return jsonify(data)

@app.route('/api/motoristas')
@auth.login_required()
def api_motoristas():
    search = request.args.get('search', '')
    operacao = get_effective_operacao()
    faixa = request.args.get('faixa', '')
    nivel = request.args.get('nivel', None)
    ano = request.args.get('ano', '')
    mes = request.args.get('mes', '')

    data = database.get_motoristas_list(search=search, operacao=operacao, faixa=faixa, nivel=nivel, ano=ano, mes=mes)
    return jsonify(data)

@app.route('/api/motorista/<codigo>')
@auth.login_required()
def api_motorista_detail(codigo):
    data = database.get_motorista_detail(codigo)
    if not data:
        return jsonify({"error": "Motorista não encontrado"}), 404

    user = g.current_user
    role = (user.get('role') or '').upper()
    if role in ['OPERACAO', 'TREINAMENTO']:
        mot = data.get('motorista') or data
        mot_op = (mot.get('operacao') or '').upper()
        user_ops = [o.strip().upper() for o in (user.get('operacao') or '').split(',') if o.strip()]
        if mot_op not in user_ops:
            return jsonify({"error": "Acesso não autorizado. Motorista de outra unidade operacional."}), 403

    try:
        historico = efetividade.get_motorista_historico(codigo)
        if historico:
            data["historico"] = historico
    except Exception as e:
        data["historico_erro"] = str(e)
    return jsonify(data)

# ══════════════════════════════════════════════════════════════
# ROTAS DE ESCRITA / CADASTROS (MATRIZ E TREINAMENTO)
# ══════════════════════════════════════════════════════════════

@app.route('/api/reciclagem/update', methods=['POST'])
@auth.login_required(allowed_roles=['MATRIZ', 'TREINAMENTO'])
def api_update_reciclagem():
    req = request.json or request.form
    rec_id = req.get('id')
    status = req.get('status')
    data_realizacao = req.get('data_realizacao')
    instrutor = req.get('instrutor')
    observacao = req.get('observacao')
    responsavel = req.get('responsavel')
    resultado = req.get('resultado')
    motivo_recusa = req.get('motivo_recusa')

    if not rec_id or not status:
        return jsonify({"error": "ID e Status são obrigatórios"}), 400

    user = g.current_user
    role = (user.get('role') or '').upper()
    if role != 'MATRIZ':
        # Valida se a reciclagem pertence a uma operacao do usuario
        conn = database.get_db_connection()
        c = conn.cursor()
        c.execute("SELECT operacao FROM reciclagens WHERE id = ?", (rec_id,))
        row = c.fetchone()
        conn.close()
        if row:
            user_ops = [o.strip().upper() for o in (user.get('operacao') or '').split(',') if o.strip()]
            if (row[0] or '').upper() not in user_ops:
                return jsonify({"error": "Acesso não autorizado. Reciclagem de outra unidade operacional."}), 403

    database.update_reciclagem_status(rec_id, status, data_realizacao, instrutor, observacao,
                                      responsavel=responsavel, resultado=resultado,
                                      motivo_recusa=motivo_recusa)
    return jsonify({"success": True, "message": "Status de reciclagem atualizado com sucesso!"})

@app.route('/api/motorista/update', methods=['POST'])
@auth.login_required(allowed_roles=['MATRIZ', 'TREINAMENTO'])
def api_update_motorista_geral():
    req = request.json or request.form
    codigo = req.get('codigo')
    if not codigo:
        return jsonify({"error": "Código do motorista é obrigatório"}), 400

    if not check_user_driver_permission(codigo):
        return jsonify({"error": "Acesso não autorizado. Motorista de outra unidade operacional."}), 403

    database.update_motorista_geral(
        codigo=codigo,
        etapa_kanban=req.get('etapa_kanban'),
        faixa_risco=req.get('faixa_risco'),
        gestor=req.get('gestor'),
        operacao=req.get('operacao'),
        reciclagem_id=req.get('reciclagem_id'),
        status_reciclagem=req.get('status_reciclagem'),
        data_realizacao=req.get('data_realizacao'),
        instrutor=req.get('instrutor'),
        observacao=req.get('observacao')
    )
    return jsonify({"success": True, "message": "Motorista atualizado com sucesso!"})

@app.route('/api/motorista/mover', methods=['POST'])
@auth.login_required(allowed_roles=['MATRIZ', 'TREINAMENTO'])
def api_mover_motorista():
    req = request.json or request.form
    codigo = req.get('codigo')
    etapa = req.get('etapa')
    if not codigo or not etapa:
        return jsonify({"error": "Código e Etapa são obrigatórios"}), 400

    if not check_user_driver_permission(codigo):
        return jsonify({"error": "Acesso não autorizado. Motorista de outra unidade operacional."}), 403

    database.mover_motorista_etapa(codigo, etapa)
    return jsonify({"success": True, "message": "Motorista movido com sucesso!"})

@app.route('/api/motorista/aprovar', methods=['POST'])
@auth.login_required(allowed_roles=['MATRIZ', 'TREINAMENTO'])
def api_aprovar_motorista():
    req = request.json or request.form
    codigo = req.get('codigo')
    if not codigo:
        return jsonify({"error": "Código do motorista é obrigatório"}), 400

    if not check_user_driver_permission(codigo):
        return jsonify({"error": "Acesso não autorizado. Motorista de outra unidade operacional."}), 403

    database.aprovar_motorista(codigo)
    return jsonify({"success": True, "message": "Motorista aprovado e concluído com sucesso!"})

@app.route('/api/importar-excel', methods=['POST'])
@auth.login_required(allowed_roles=['MATRIZ', 'TREINAMENTO'])
def api_importar_excel():
    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nenhum arquivo selecionado"}), 400

    _name = (file.filename or '').lower()
    if not _name.endswith(('.xlsx', '.xls')):
        return jsonify({"error": "Formato inválido: envie .xlsx ou .xls"}), 400
    if request.content_length and request.content_length > MAX_UPLOAD_BYTES:
        return jsonify({"error": "Arquivo excede o limite de 25MB"}), 400

    try:
        xl = pd.ExcelFile(file)
        sheet_name = 'BASE' if 'BASE' in xl.sheet_names else xl.sheet_names[0]
        df = pd.read_excel(xl, sheet_name=sheet_name)

        stats = database.process_excel_dataframe(df)
        return jsonify({
            "success": True,
            "message": f"Planilha '{file.filename}' importada com sucesso!",
            "stats": stats
        })
    except Exception as e:
        return jsonify({"error": f"Erro ao processar planilha: {str(e)}"}), 500

@app.route('/api/pdi/add', methods=['POST'])
@auth.login_required(allowed_roles=['MATRIZ', 'TREINAMENTO'])
def api_add_pdi():
    req = request.json or request.form
    codigo = req.get('motorista_codigo')
    nivel = int(req.get('nivel', 3))
    tipo_acao = req.get('tipo_acao', 'PDI')
    descricao = req.get('descricao', '')
    prazo = req.get('prazo', '')
    responsavel = req.get('responsavel', '')

    if not codigo or not descricao:
        return jsonify({"error": "Motorista e Descrição da ação são obrigatórios"}), 400

    if not check_user_driver_permission(codigo):
        return jsonify({"error": "Acesso não autorizado. Motorista de outra unidade operacional."}), 403

    database.add_pdi_record(codigo, nivel, tipo_acao, descricao, prazo, responsavel)
    return jsonify({"success": True, "message": "Plano de Ação / PDI criado com sucesso!"})

@app.route('/api/efetividade-kpis')
@auth.login_required()
def api_efetividade_kpis():
    operacao = get_effective_operacao()
    ano = request.args.get('ano', '')
    mes = request.args.get('mes', '')
    data = efetividade.get_efetividade_kpis(operacao=operacao, ano=ano, mes=mes)
    return jsonify(data)

@app.route('/api/evolucao-efetividade')
@auth.login_required()
def api_evolucao_efetividade():
    operacao = get_effective_operacao()
    ano = request.args.get('ano', '')
    mes = request.args.get('mes', '')
    return jsonify({
        "mensal": efetividade.get_evolucao_mensal(operacao=operacao, ano=ano, mes=mes),
        "por_operacao": efetividade.get_evolucao_por_operacao(operacao=operacao, ano=ano, mes=mes)
    })

@app.route('/api/reincidentes')
@auth.login_required()
def api_reincidentes():
    operacao = get_effective_operacao()
    ano = request.args.get('ano', '')
    mes = request.args.get('mes', '')
    apenas_alerta = request.args.get('apenas_alerta', '0') == '1'
    data = efetividade.get_reincidentes_detalhado(operacao=operacao, ano=ano, mes=mes,
                                                  apenas_alerta=apenas_alerta)
    return jsonify(data)

@app.route('/api/config/regras', methods=['GET', 'POST'])
@auth.login_required()
def api_config_regras():
    if request.method == 'POST':
        user = g.current_user
        if user.get('role') != 'MATRIZ':
            return jsonify({'error': 'Apenas a Matriz pode alterar regras do sistema.'}), 403
            
        req = request.json or request.form or {}
        try:
            for chave in ('reincidencia_meses_consecutivos',
                          'premiacao_percentual_impacto',
                          'regra_reincidencia_ativa',
                          'regra_premiacao_ativa'):
                if chave in req and req[chave] is not None:
                    valor = req[chave]
                    if isinstance(valor, bool):
                        valor = '1' if valor else '0'
                    efetividade.set_config(chave, valor)
            return jsonify({"success": True, "message": "Regras atualizadas com sucesso!",
                            "regras": efetividade.get_regras_config()})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify(efetividade.get_regras_config())

@app.route('/api/filters-options')
@auth.login_required()
def api_filters_options():
    user = g.current_user
    conn = database.get_db_connection()
    cursor = conn.cursor()
    role = (user.get('role') or '').upper()

    if role in ['OPERACAO', 'TREINAMENTO']:
        raw_ops = [o.strip() for o in (user.get('operacao') or '').split(',') if o.strip()]
        if raw_ops:
            ph = ','.join(['?'] * len(raw_ops))
            cursor.execute(f"SELECT DISTINCT operacao FROM motoristas WHERE operacao IN ({ph}) ORDER BY operacao ASC", raw_ops)
            operacoes = [r[0] for r in cursor.fetchall() if r[0]]
            for o in raw_ops:
                if o not in operacoes:
                    operacoes.append(o)
            operacoes.sort()

            cursor.execute(f"SELECT DISTINCT gestor FROM motoristas WHERE operacao IN ({ph}) AND gestor IS NOT NULL AND gestor != '' ORDER BY gestor ASC", raw_ops)
            gestores = [r[0] for r in cursor.fetchall() if r[0]]
        else:
            operacoes = []
            gestores = []
    else:
        cursor.execute("SELECT DISTINCT operacao FROM motoristas ORDER BY operacao ASC")
        operacoes = [r[0] for r in cursor.fetchall() if r[0]]

        cursor.execute("SELECT DISTINCT gestor FROM motoristas WHERE gestor IS NOT NULL AND gestor != '' ORDER BY gestor ASC")
        gestores = [r[0] for r in cursor.fetchall() if r[0]]

    cursor.execute("SELECT DISTINCT mes FROM reciclagens ORDER BY mes ASC")
    meses = [r[0] for r in cursor.fetchall() if r[0]]

    cursor.execute("SELECT DISTINCT ano FROM reciclagens ORDER BY ano DESC")
    anos = [r[0] for r in cursor.fetchall() if r[0]]

    meses_anos = database.get_meses_anos_existentes()
    conn.close()

    return jsonify({
        "operacoes": operacoes,
        "gestores": gestores,
        "meses": meses,
        "anos": anos,
        "meses_anos": meses_anos,
        "user_role": role,
        "user_op": user.get('operacao', '')
    })

@app.route('/api/config/limpar-banco', methods=['POST'])
@auth.login_required(allowed_roles=['MATRIZ'])
def api_config_limpar_banco():
    try:
        database.limpar_banco_dados_total()
        return jsonify({"success": True, "message": "Banco de dados limpo com sucesso!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/config/excluir-mes', methods=['POST'])
@auth.login_required(allowed_roles=['MATRIZ'])
def api_config_excluir_mes():
    req = request.json or {}
    mes = req.get('mes')
    ano = req.get('ano')
    if not mes or not ano:
        return jsonify({"error": "Mês e Ano são obrigatórios"}), 400
    try:
        database.excluir_reciclagens_mes_ano(mes, ano)
        return jsonify({"success": True, "message": f"Reciclagens de Mês {mes}/{ano} excluídas com sucesso!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/exportar-excel')
@auth.login_required()
def api_exportar_excel():
    user = g.current_user
    conn = database.get_db_connection()
    role = (user.get('role') or '').upper()

    if role in ['OPERACAO', 'TREINAMENTO']:
        user_ops = [o.strip().upper() for o in (user.get('operacao') or '').split(',') if o.strip()]
        if not user_ops:
            user_ops = ['__NONE__']
        ph = ','.join(['?'] * len(user_ops))
        df_mot = pd.read_sql_query(f"SELECT * FROM motoristas WHERE UPPER(operacao) IN ({ph}) ORDER BY total_reciclagens_12m DESC", conn, params=user_ops)
        df_rec = pd.read_sql_query(f"SELECT * FROM reciclagens WHERE UPPER(operacao) IN ({ph}) ORDER BY ano DESC, mes DESC", conn, params=user_ops)
        df_pdi = pd.read_sql_query(f"SELECT p.* FROM pdis_comites p JOIN motoristas m ON p.motorista_codigo = m.codigo WHERE UPPER(m.operacao) IN ({ph}) ORDER BY p.id DESC", conn, params=user_ops)
    else:
        df_mot = pd.read_sql_query("SELECT * FROM motoristas ORDER BY total_reciclagens_12m DESC", conn)
        df_rec = pd.read_sql_query("SELECT * FROM reciclagens ORDER BY ano DESC, mes DESC", conn)
        df_pdi = pd.read_sql_query("SELECT p.* FROM pdis_comites ORDER BY id DESC", conn)

    conn.close()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_mot.to_excel(writer, sheet_name='MOTORISTAS_PGCSC', index=False)
        df_rec.to_excel(writer, sheet_name='HISTORICO_RECICLAGENS', index=False)
        df_pdi.to_excel(writer, sheet_name='PDIS_E_COMITES', index=False)

    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='PGCSC_Controle_Reciclagens_Export.xlsx'
    )

if __name__ == '__main__':
    print("Iniciando Servidor Web PGCSC Expresso Nepomuceno...")
    app.run(host='127.0.0.1', port=5000, debug=False)
