import sys
import os
import datetime
import psycopg2
import ollama

if len(sys.argv) < 5:
    print("Uso: python salvar_pendencia_sanitizado.py <pergunta> <categoria_id> <subcategoria_id> <usuario_id>")
    sys.exit(1)

pergunta = sys.argv[1]
categoria_id_input = int(sys.argv[2])
subcategoria_id_input = int(sys.argv[3])
usuario_id = int(sys.argv[4])

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_PORT = os.environ.get("DB_PORT", "5432")

try:
    response = ollama.chat(model=os.environ.get("OLLAMA_MODEL", "mistral"), messages=[
        {"role": "system", "content": "Você é uma IA que ajuda a categorizar perguntas que não foram respondidas pela base de conhecimento."},
        {"role": "user", "content": f"Resumo breve e direto desta pergunta para que possa ser cadastrada como novo assunto: {pergunta}"}
    ])
    resumo = response.get("message", {}).get("content", "")
    if not resumo:
        resumo = response.get("content", "") or pergunta[:200]
    resumo = resumo.strip()
except Exception:
    resumo = pergunta[:200]

conn = None
try:
    conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, port=DB_PORT)
    cur = conn.cursor()
    resumo_lower = resumo.lower()
    cur.execute("SELECT categoria_id, nome FROM bloqueio_v2.categoria")
    categorias = cur.fetchall()
    categoria_encontrada = None
    for cat_id, nome_cat in categorias:
        if nome_cat and nome_cat.lower() in resumo_lower:
            categoria_encontrada = cat_id
            break
    if not categoria_encontrada:
        cur.execute("SELECT categoria_id FROM bloqueio_v2.categoria WHERE LOWER(nome) = LOWER(%s)", ("Outros",))
        row = cur.fetchone()
        if row:
            categoria_encontrada = row[0]
        else:
            cur.execute("INSERT INTO bloqueio_v2.categoria (nome, descricao) VALUES (%s, %s) RETURNING categoria_id", ("Outros", "Criada automaticamente"))
            categoria_encontrada = cur.fetchone()[0]
            conn.commit()
    cur.execute("SELECT subcategoria_id, nome FROM bloqueio_v2.subcategoria WHERE categoria_id = %s", (categoria_encontrada,))
    subcategorias = cur.fetchall()
    subcategoria_encontrada = None
    for sub_id, nome_sub in subcategorias:
        if nome_sub and nome_sub.lower() in resumo_lower:
            subcategoria_encontrada = sub_id
            break
    if not subcategoria_encontrada:
        cur.execute("SELECT subcategoria_id FROM bloqueio_v2.subcategoria WHERE categoria_id = %s AND nome ILIKE %s", (categoria_encontrada, "Outros"))
        row = cur.fetchone()
        if row:
            subcategoria_encontrada = row[0]
        else:
            cur.execute("INSERT INTO bloqueio_v2.subcategoria (categoria_id, nome, descricao) VALUES (%s, %s, %s) RETURNING subcategoria_id", (categoria_encontrada, "Outros", "Criada automaticamente"))
            subcategoria_encontrada = cur.fetchone()[0]
            conn.commit()
    cur.execute("""
        INSERT INTO bloqueio_v2.assunto_pendente (
            consulta_id,
            texto_assunto,
            status,
            datahora_sugestao,
            categoria_id,
            subcategoria_id,
            aprovado_por,
            datahora_validacao
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (None, resumo, "Pendente", datetime.datetime.now(), categoria_encontrada, subcategoria_encontrada, None, None))
    conn.commit()
    cur.close()
    conn.close()
    print("Assunto pendente salvo com sucesso.")
except Exception as e:
    if conn:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
    print(f"Erro ao salvar pendência: {e}")
