
import sqlite3
import auth

# 1. Clear password_hash and old tokens for root
conn = auth.get_db()
c = conn.cursor()
c.execute("UPDATE usuarios SET password_hash = NULL WHERE email = 'matheuscamilio@expressonepomuceno.com.br'")
c.execute("UPDATE auth_tokens SET used = 1 WHERE user_id = (SELECT id FROM usuarios WHERE email = 'matheuscamilio@expressonepomuceno.com.br')")
conn.commit()

# 2. Get user
user = auth.get_user_by_email('matheuscamilio@expressonepomuceno.com.br')
print("USER RECORD:", user)

# 3. Create fresh token
token = auth.create_auth_token(user['id'], tipo='setup_password', expires_minutes=1440) # 24h
setup_url = f"https://decamservice.com/telemetria/auth/setup-password?token={token}"
print(f"NEW SETUP URL: {setup_url}")

# 4. Send email via Brevo relay
try:
    auth.send_auth_email(user['email'], user['nome'], token, tipo='setup_password')
    print("EMAIL_SENT_SUCCESS")
except Exception as e:
    print(f"EMAIL_ERROR: {e}")
