import os
import sqlite3
import hashlib
import hmac
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from datetime import datetime, timedelta
from functools import wraps
from flask import request, redirect, url_for, jsonify, g

DB_PATH = os.path.join(os.path.dirname(__file__), 'reciclagem.db')
SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp-relay.brevo.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', 'a89907001@smtp-brevo.com')
SMTP_PASS = os.environ.get('SMTP_PASS', '')
SMTP_FROM = os.environ.get('SMTP_FROM', 'nao-responda@decamservice.com')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 100000).hex()
    return f"{salt}${h}"

def verify_password(stored_hash: str, password: str) -> bool:
    if not stored_hash or '$' not in stored_hash:
        return False
    salt, h = stored_hash.split('$', 1)
    calc = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 100000).hex()
    return hmac.compare_digest(calc, h)

def init_auth_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        nome TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'OPERACAO',
        operacao TEXT NOT NULL DEFAULT '',
        telefone TEXT DEFAULT NULL,
        password_hash TEXT DEFAULT NULL,
        ativo INTEGER NOT NULL DEFAULT 1,
        ultimo_acesso DATETIME DEFAULT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    try:
        c.execute('ALTER TABLE usuarios ADD COLUMN telefone TEXT DEFAULT NULL')
    except Exception:
        pass

    c.execute('''
    CREATE TABLE IF NOT EXISTS auth_tokens (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        tipo TEXT NOT NULL DEFAULT 'setup_password',
        expires_at DATETIME NOT NULL,
        used INTEGER NOT NULL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES usuarios(id) ON DELETE CASCADE
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS user_sessions (
        session_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        expires_at DATETIME NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES usuarios(id) ON DELETE CASCADE
    )
    ''')
    conn.commit()
    conn.close()

def get_user_by_email(email: str):
    email_clean = (email or '').strip().lower()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM usuarios WHERE LOWER(email) = ?', (email_clean,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM usuarios WHERE id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def normalize_phone(raw: str) -> str:
    if not raw:
        return None
    import re
    digits = re.sub(r'\D', '', str(raw))
    while digits.startswith('0'):
        digits = digits[1:]
    if len(digits) in (10, 11):
        return f"55{digits}"
    if digits.startswith('55') and len(digits) in (12, 13):
        return digits
    if len(digits) >= 8:
        return digits
    return None

def _normalize_ops(operacao):
    if not operacao:
        return ''
    if isinstance(operacao, (list, tuple, set)):
        items = operacao
    else:
        items = str(operacao).split(',')
    clean_items = [str(o).strip().upper() for o in items if str(o).strip()]
    return ', '.join(clean_items)

def create_user(email: str, nome: str, role: str = 'OPERACAO', operacao: str = '', password: str = None, telefone: str = None):
    email_clean = (email or '').strip().lower()
    nome_clean = (nome or '').strip()
    r = (role or '').upper().strip()
    if r == 'MATRIZ':
        role_clean = 'MATRIZ'
    elif r == 'TREINAMENTO':
        role_clean = 'TREINAMENTO'
    else:
        role_clean = 'OPERACAO'

    operacao_clean = '' if role_clean == 'MATRIZ' else _normalize_ops(operacao)
    pw_hash = hash_password(password) if password else None
    phone_clean = normalize_phone(telefone)

    conn = get_db()
    c = conn.cursor()
    c.execute('''
    INSERT INTO usuarios (email, nome, role, operacao, telefone, password_hash, ativo)
    VALUES (?, ?, ?, ?, ?, ?, 1)
    ''', (email_clean, nome_clean, role_clean, operacao_clean, phone_clean, pw_hash))
    user_id = c.lastrowid
    conn.commit()
    conn.close()
    return get_user_by_id(user_id)

def update_user(user_id: int, nome: str, email: str, role: str, operacao, telefone: str = None):
    email_clean = (email or '').strip().lower()
    nome_clean = (nome or '').strip()
    r = (role or '').upper().strip()
    if r == 'MATRIZ':
        role_clean = 'MATRIZ'
    elif r == 'TREINAMENTO':
        role_clean = 'TREINAMENTO'
    else:
        role_clean = 'OPERACAO'

    operacao_clean = '' if role_clean == 'MATRIZ' else _normalize_ops(operacao)
    phone_clean = normalize_phone(telefone)

    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id FROM usuarios WHERE LOWER(email) = ? AND id != ?', (email_clean, user_id))
    if c.fetchone():
        conn.close()
        raise ValueError('Já existe outro usuário com este e-mail.')

    c.execute('''
    UPDATE usuarios
    SET nome = ?, email = ?, role = ?, operacao = ?, telefone = ?
    WHERE id = ?
    ''', (nome_clean, email_clean, role_clean, operacao_clean, phone_clean, user_id))
    conn.commit()
    conn.close()
    return get_user_by_id(user_id)

def update_user_phone(user_id: int, telefone: str):
    phone_clean = normalize_phone(telefone)
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE usuarios SET telefone = ? WHERE id = ?', (phone_clean, user_id))
    conn.commit()
    conn.close()
    return get_user_by_id(user_id)

def update_user_password(user_id: int, password: str):
    pw_hash = hash_password(password)
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE usuarios SET password_hash = ? WHERE id = ?', (pw_hash, user_id))
    conn.commit()
    conn.close()

def update_user_last_login(user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE usuarios SET ultimo_acesso = CURRENT_TIMESTAMP WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()

def create_auth_token(user_id: int, tipo: str = 'setup_password', expires_minutes: int = 120) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=expires_minutes)
    conn = get_db()
    c = conn.cursor()
    c.execute('''
    INSERT INTO auth_tokens (token, user_id, tipo, expires_at, used)
    VALUES (?, ?, ?, ?, 0)
    ''', (token, user_id, tipo, expires_at.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()
    return token

def verify_and_consume_token(token: str, tipo: str = None):
    if not token:
        return None
    conn = get_db()
    c = conn.cursor()
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    if tipo:
        c.execute('''
        SELECT t.*, u.email, u.nome, u.role, u.operacao, u.ativo, u.password_hash
        FROM auth_tokens t
        JOIN usuarios u ON t.user_id = u.id
        WHERE t.token = ? AND t.tipo = ? AND t.used = 0 AND t.expires_at > ?
        ''', (token, tipo, now_str))
    else:
        c.execute('''
        SELECT t.*, u.email, u.nome, u.role, u.operacao, u.ativo, u.password_hash
        FROM auth_tokens t
        JOIN usuarios u ON t.user_id = u.id
        WHERE t.token = ? AND t.used = 0 AND t.expires_at > ?
        ''', (token, now_str))
        
    row = c.fetchone()
    if not row:
        conn.close()
        return None

    # Invalida o token para impedir reutilizacao
    c.execute('UPDATE auth_tokens SET used = 1 WHERE token = ?', (token,))
    conn.commit()
    conn.close()
    return dict(row)

def create_session(user_id: int, days: int = 14) -> str:
    session_id = secrets.token_urlsafe(40)
    expires_at = datetime.utcnow() + timedelta(days=days)
    conn = get_db()
    c = conn.cursor()
    c.execute('''
    INSERT INTO user_sessions (session_id, user_id, expires_at)
    VALUES (?, ?, ?)
    ''', (session_id, user_id, expires_at.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()
    update_user_last_login(user_id)
    return session_id

def get_session_user(session_id: str):
    if not session_id:
        return None
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    c = conn.cursor()
    c.execute('''
    SELECT u.id, u.email, u.nome, u.role, u.operacao, u.ativo, u.created_at, s.expires_at
    FROM user_sessions s
    JOIN usuarios u ON s.user_id = u.id
    WHERE s.session_id = ? AND s.expires_at > ? AND u.ativo = 1
    ''', (session_id, now_str))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_session(session_id: str):
    if not session_id:
        return
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM user_sessions WHERE session_id = ?', (session_id,))
    conn.commit()
    conn.close()

def list_users():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
    SELECT id, email, nome, role, operacao, telefone, ativo, ultimo_acesso, created_at,
           (CASE WHEN password_hash IS NOT NULL THEN 1 ELSE 0 END) as has_password
    FROM usuarios
    ORDER BY (CASE WHEN role='MATRIZ' THEN 1 WHEN role='TREINAMENTO' THEN 2 ELSE 3 END) ASC, nome ASC
    ''')
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def send_auth_whatsapp(phone: str, nome: str, token: str, tipo: str = 'setup_password', base_url: str = 'https://decamservice.com/telemetria'):
    import urllib.request
    import urllib.parse
    import json
    
    clean_phone = normalize_phone(phone)
    if not clean_phone:
        raise ValueError("Número de telefone/WhatsApp inválido.")

    base_clean = (base_url or 'https://decamservice.com/telemetria').rstrip('/')
    action_url = f"{base_clean}/auth/setup-password?token={token}"
    primeiro_nome = (nome or 'Colega').strip().split()[0]
    
    if tipo == 'forgot_password':
        header = f"Olá, *{primeiro_nome}*! 👋"
        body = "Você solicitou a *redefinição da sua senha* no sistema *PGCSC Telemetria* (Expresso Nepomuceno)."
    else:
        header = f"Olá, *{primeiro_nome}*! 👋"
        body = "Você foi cadastrado na plataforma *PGCSC Telemetria* da *Expresso Nepomuceno*!"

    message = (
        f"{header}\n\n"
        f"{body}\n\n"
        f"Para cadastrar sua senha de acesso com segurança, clique no link abaixo:\n\n"
        f"{action_url}\n\n"
        f"⏱️ _Link válido por 2 horas._\n\n"
        f"💡 _Se o link acima não estiver clicável, responda esta mensagem com um *OK* para liberar o link no WhatsApp._"
    )

    wa_web_url = f"https://wa.me/{clean_phone}?text={urllib.parse.quote(message)}"

    url = "http://ridecheck-whatsapp:3005/send"
    payload = json.dumps({
        "phone": clean_phone,
        "message": message,
        "sendPdf": False
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_body = resp.read().decode("utf-8")
            data = json.loads(resp_body) if resp_body else {}
            data['whatsapp_web_url'] = wa_web_url
            return data
    except Exception as e:
        # Retorna o link web mesmo se der erro no robô para o usuário poder usar wa.me como fallback
        raise RuntimeError(f"Erro no robô WhatsApp: {str(e)}")

def update_user_status(user_id: int, ativo: int):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE usuarios SET ativo = ? WHERE id = ?', (1 if ativo else 0, user_id))
    if not ativo:
        c.execute('DELETE FROM user_sessions WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def delete_user(user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM user_sessions WHERE user_id = ?', (user_id,))
    c.execute('DELETE FROM auth_tokens WHERE user_id = ?', (user_id,))
    c.execute('DELETE FROM usuarios WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()

def send_auth_email(to_email: str, nome: str, token: str, tipo: str = 'setup_password', base_url: str = 'https://decamservice.com/telemetria'):
    base_clean = (base_url or 'https://decamservice.com/telemetria').rstrip('/')
    action_url = f"{base_clean}/auth/setup-password?token={token}"
    
    if tipo == 'forgot_password':
        subject = "Redefinir Senha de Acesso - PGCSC Telemetria"
        btn_text = "Redefinir Minha Senha"
    else:
        subject = "Cadastrar Senha de Acesso - PGCSC Telemetria"
        btn_text = "Cadastrar Minha Senha"

    html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:32px 14px;background-color:#0b1329;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#f1f5f9;">
  <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:440px;background-color:#111c38;border:1px solid rgba(255,255,255,0.12);border-radius:18px;overflow:hidden;box-shadow:0 14px 40px rgba(0,0,0,0.5);">
    <tr>
      <td style="padding:22px 24px;background:linear-gradient(135deg,#0d1b2a,#1a365d);border-bottom:1px solid rgba(255,255,255,0.08);text-align:center;">
        <div style="color:#ffffff;font-size:16px;font-weight:800;letter-spacing:-0.02em;">EXPRESSO <span style="color:#38bdf8;">NEPOMUCENO</span></div>
        <div style="color:#93c5fd;font-size:10.5px;margin-top:3px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;">PGCSC Telemetria</div>
      </td>
    </tr>
    <tr>
      <td style="padding:32px 24px;text-align:center;">
        <h2 style="margin:0 0 12px 0;font-size:18px;font-weight:700;color:#ffffff;">Olá, {nome}!</h2>
        <p style="margin:0 0 24px 0;font-size:13.5px;color:#cbd5e1;line-height:1.5;">
          Clique no botão abaixo para cadastrar sua senha de acesso ao sistema:
        </p>
        
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin:0 auto 20px auto;">
          <tr>
            <td align="center">
              <a href="{action_url}" target="_blank" style="display:inline-block;padding:14px 32px;font-size:14px;font-weight:800;color:#ffffff;background:linear-gradient(135deg,#2563eb,#1d4ed8);text-decoration:none;border-radius:10px;box-shadow:0 4px 16px rgba(37,99,235,0.4);">
                {btn_text}
              </a>
            </td>
          </tr>
        </table>
        
        <p style="margin:0;font-size:11px;color:#64748b;">
          Link de uso único válido por 2 horas.
        </p>
      </td>
    </tr>
    <tr>
      <td style="padding:12px 24px;background-color:#080f20;border-top:1px solid rgba(255,255,255,0.06);font-size:10.5px;color:#64748b;text-align:center;">
        Expresso Nepomuceno S/A • Telemetria
      </td>
    </tr>
  </table>
</body>
</html>
"""

    text = f"""Olá, {nome}!

Clique no link abaixo para cadastrar sua senha de acesso ao PGCSC Telemetria:
{action_url}

Este link expira em 2 horas e é de uso único.

Expresso Nepomuceno - Plataforma PGCSC
"""

    msg = MIMEMultipart("alternative")
    msg["From"] = f"PGCSC Telemetria <{SMTP_FROM}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="decamservice.com")
    msg["Reply-To"] = "nao-responda@decamservice.com"

    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    s = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
    s.starttls()
    if SMTP_USER and SMTP_PASS:
        try:
            s.login(SMTP_USER, SMTP_PASS)
        except Exception:
            pass
    s.sendmail(SMTP_FROM, [to_email], msg.as_string())
    s.quit()
    return True

def get_current_user():
    session_id = request.cookies.get('pgcsc_session')
    if not session_id:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            session_id = auth_header.split(' ', 1)[1].strip()
    if not session_id:
        return None
    return get_session_user(session_id)

def login_required(allowed_roles=None):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            user = get_current_user()
            if not user:
                if request.path.startswith('/api/'):
                    return jsonify({'error': 'Não autenticado. Faça login para continuar.', 'code': 'UNAUTHORIZED'}), 401
                return redirect(url_for('login_view', next=request.path))
            
            if not user.get('ativo', 1):
                if request.path.startswith('/api/'):
                    return jsonify({'error': 'Usuário desativado.', 'code': 'FORBIDDEN'}), 403
                return redirect(url_for('login_view', error='inactive'))

            if allowed_roles:
                user_role = (user.get('role') or '').upper()
                if user_role not in [r.upper() for r in allowed_roles]:
                    if request.path.startswith('/api/'):
                        return jsonify({'error': 'Acesso negado. Perfil sem permissão para esta ação.', 'code': 'FORBIDDEN'}), 403
                    return redirect(url_for('index'))

            g.current_user = user
            return fn(*args, **kwargs)
        return wrapped
    return decorator
