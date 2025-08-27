import os
import requests
import openai
import psycopg2
from docx import Document
import json
import sys
from contextlib import closing

openai.api_key = os.environ.get("OPENAI_API_KEY", "")

DOCUMENT_URL = os.environ.get("DOCUMENT_URL", "")
ARQUIVO_LOCAL = os.environ.get("ARQUIVO_LOCAL", "bloqueio_cartao.docx")
TITULO = os.environ.get("TITULO", "Bloqueio de Cartão de Crédito")
TIPO = os.environ.get("TIPO", "Texto")
URL_ARQUIVO = os.environ.get("URL_ARQUIVO", DOCUMENT_URL)
SUBCATEGORIA_ID = int(os.environ.get("SUBCATEGORIA_ID", "1"))

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_PORT = os.environ.get("DB_PORT", "5432")

if not openai.api_key:
    print("OPENAI_API_KEY não definida. Abortando.")
    sys.exit(1)

if not DOCUMENT_URL:
    print("DOCUMENT_URL não definida. Abortando.")
    sys.exit(1)

try:
    resp = requests.get(DOCUMENT_URL, timeout=30)
    resp.raise_for_status()
    with open(ARQUIVO_LOCAL, "wb") as f:
        f.write(resp.content)
except Exception as e:
    print(f"Falha ao baixar o documento: {e}")
    sys.exit(1)

try:
    doc = Document(ARQUIVO_LOCAL)
    texto_concatenado = "\n".join([p.text for p in doc.paragraphs if p.text.strip() != ""])
except Exception as e:
    print(f"Falha ao ler .docx: {e}")
    sys.exit(1)

try:
    embedding_response = openai.Embedding.create(
        input=texto_concatenado,
        model="text-embedding-ada-002"
    )
    vetor = embedding_response["data"][0]["embedding"]
except Exception as e:
    print(f"Erro ao gerar embedding: {e}")
    sys.exit(1)

conn = None
try:
    conn = psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )
    with closing(conn.cursor()) as cursor:
        cursor.execute(
            """
            INSERT INTO bloqueio_v2.documento (titulo, tipo, url_arquivo, data_inclusao, subcategoria_id)
            VALUES (%s, %s, %s, CURRENT_DATE, %s)
            RETURNING documento_id;
            """,
            (TITULO, TIPO, URL_ARQUIVO, SUBCATEGORIA_ID)
        )
        documento_id_row = cursor.fetchone()
        if not documento_id_row:
            raise RuntimeError("Não foi possível obter documento_id retornado pelo INSERT.")
        documento_id = documento_id_row[0]

        cursor.execute(
            """
            INSERT INTO bloqueio_v2.documento_embedding (documento_id, texto_concatenado, embedding)
            VALUES (%s, %s, %s);
            """,
            (documento_id, texto_concatenado, json.dumps(vetor))
        )

    conn.commit()
    print("Documento salvo com embedding no PostgreSQL.")
except Exception as e:
    if conn:
        conn.rollback()
    print(f"Erro ao inserir no banco: {e}")
    sys.exit(1)
finally:
    if conn:
        conn.close()
