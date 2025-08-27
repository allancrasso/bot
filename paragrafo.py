import openai
import psycopg2
import requests
from docx import Document
import os
import json
import sys
from contextlib import closing

openai.api_key = os.environ.get("OPENAI_API_KEY", "")

ARQUIVO_LOCAL = os.environ.get("ARQUIVO_LOCAL", "documento_temp.docx")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_PORT = os.environ.get("DB_PORT", "5432")

def gerar_embedding(texto):
    resp = openai.Embedding.create(input=texto, model="text-embedding-ada-002")
    return resp["data"][0]["embedding"]

def listar_documentos_salvos(cursor):
    try:
        cursor.execute(
            """
            SELECT documento_id, titulo, url_arquivo, data_inclusao
            FROM bloqueio_v2.documento
            ORDER BY data_inclusao DESC
            """
        )
        documentos = cursor.fetchall()
        print(" Documentos disponíveis no banco:\n")
        for doc in documentos:
            print(f" ID: {doc[0]} |  Título: {doc[1]} |  URL: {doc[2]} |  Data: {doc[3]}")
        return documentos
    except Exception as e:
        print(f"Erro ao listar documentos: {e}")
        return []

def processar_documento(conn, cursor, documento_id, documento_url):
    try:
        resp = requests.get(documento_url, timeout=30)
        resp.raise_for_status()
        with open(ARQUIVO_LOCAL, "wb") as f:
            f.write(resp.content)
    except Exception as e:
        print(f"Falha ao baixar o documento: {e}")
        return

    try:
        doc = Document(ARQUIVO_LOCAL)
        paragrafos = [p.text.strip() for p in doc.paragraphs if len(p.text.strip()) > 20]
        print(f"Total de parágrafos com conteúdo relevante: {len(paragrafos)}")
    except Exception as e:
        print(f"Falha ao ler .docx: {e}")
        return

    try:
        cursor.execute(
            """
            SELECT paragrafo FROM bloqueio_v2.documento_paragrafo_embedding
            WHERE documento_id = %s
            """,
            (documento_id,),
        )
        paragrafos_existentes = set(row[0] for row in cursor.fetchall())
    except Exception as e:
        print(f"Erro ao verificar parágrafos existentes: {e}")
        paragrafos_existentes = set()

    novos_paragrafos = [p for p in paragrafos if p not in paragrafos_existentes]
    print(f"Novos parágrafos a processar: {len(novos_paragrafos)}")

    for i, par in enumerate(novos_paragrafos):
        try:
            embedding = gerar_embedding(par)
            cursor.execute(
                """
                INSERT INTO bloqueio_v2.documento_paragrafo_embedding (documento_id, paragrafo, embedding)
                VALUES (%s, %s, %s)
                """,
                (documento_id, par, json.dumps(embedding)),
            )
            print(f"Parágrafo {i+1} inserido.")
        except Exception as e:
            print(f"Erro ao inserir parágrafo {i+1}: {e}")

    try:
        conn.commit()
        print("Processamento concluído!")
    except Exception as e:
        conn.rollback()
        print(f"Erro ao commitar transação: {e}")
    finally:
        if os.path.exists(ARQUIVO_LOCAL):
            try:
                os.remove(ARQUIVO_LOCAL)
            except Exception:
                pass

if __name__ == "__main__":
    if not openai.api_key:
        print("OPENAI_API_KEY não definida. Abortando.")
        sys.exit(1)

    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
        )
        with closing(conn.cursor()) as cursor:
            documentos = listar_documentos_salvos(cursor)
            if not documentos:
                print("Nenhum documento encontrado.")
            else:
                try:
                    doc_id = int(input("\nDigite o ID do documento que deseja processar: "))
                    selected = [d for d in documentos if d[0] == doc_id]
                    if selected:
                        processar_documento(conn, cursor, documento_id=doc_id, documento_url=selected[0][2])
                    else:
                        print("Documento não encontrado.")
                except ValueError:
                    print("ID inválido. Digite um número.")
                except Exception as e:
                    print(f"Erro: {e}")
    except Exception as e:
        print(f"Erro de conexão com o banco: {e}")
    finally:
        if conn:
            conn.close()
