import tkinter as tk
from tkinter import ttk, messagebox
import openai
import psycopg2
import numpy as np
import json
import os
import subprocess

openai.api_key = os.environ.get("OPENAI_API_KEY", "")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_PORT = os.environ.get("DB_PORT", "5432")

try:
    conn = psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )
    cursor = conn.cursor()
except Exception as e:
    conn = None
    cursor = None

CACHE_FILE = "cache_respostas.json"

def carregar_categorias():
    if not cursor:
        return []
    cursor.execute("SELECT categoria_id, nome FROM bloqueio_v2.categoria")
    return cursor.fetchall()

def carregar_subcategorias(event):
    if not cursor:
        return
    cat_texto = categoria_var.get()
    if not cat_texto:
        return
    try:
        categoria_id = int(cat_texto.split(" - ")[0])
        cursor.execute("SELECT subcategoria_id, nome FROM bloqueio_v2.subcategoria WHERE categoria_id = %s", (categoria_id,))
        subcats = cursor.fetchall()
        if subcats:
            subcategoria_combo['values'] = [f"{id} - {nome}" for id, nome in subcats]
            subcategoria_combo.set('')
        else:
            subcategoria_combo['values'] = []
            subcategoria_combo.set('Sem subcategorias')
    except Exception as e:
        messagebox.showerror("Erro", f"Erro ao carregar subcategorias: {e}")

def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def gerar_resposta_humana(pergunta, paragrafo):
    prompt = (
        f"Pergunta: {pergunta}\n\n"
        f"Trecho relevante do documento: {paragrafo}\n\n"
        f"Responda de forma clara, empática e humanizada para ajudar o usuário:"
    )
    try:
        chat_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um atendente educado e prestativo de uma central de atendimento."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return chat_response.choices[0].message.content.strip()
    except Exception as e:
        return f"(Erro ao gerar resposta humanizada: {e})\n\n{paragrafo}"

def buscar_resposta():
    if not cursor:
        messagebox.showerror("Erro", "Conexão com banco de dados não disponível.")
        return

    subcat_texto = subcategoria_var.get()
    pergunta = pergunta_entry.get().strip()

    if not subcat_texto or not pergunta:
        messagebox.showwarning("Atenção", "Escolha uma subcategoria e digite sua pergunta.")
        return

    subcategoria_id = int(subcat_texto.split(" - ")[0])
    resposta_output.delete('1.0', tk.END)
    resposta_output.insert(tk.END, "Buscando resposta, por favor aguarde...\n")
    app.update()

    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        else:
            cache = {}

        chave_cache = f"{subcategoria_id}|{pergunta.lower()}"
        if chave_cache in cache:
            resposta = cache[chave_cache]
            resposta_output.delete('1.0', tk.END)
            resposta_output.insert(tk.END, f"{resposta['resposta']}\n\n🔗 {resposta['url']}\n📈 Similaridade: {resposta['score']:.4f} (cache)")
            return

        cursor.execute("""
            SELECT d.documento_id, d.url_arquivo, d.titulo, p.palavra
            FROM bloqueio_v2.documento d
            JOIN bloqueio_v2.documento_palavra_chave p ON d.documento_id = p.documento_id
            WHERE d.subcategoria_id = %s
        """, (subcategoria_id,))
        palavras_chave_resultados = cursor.fetchall()
        palavras_encontradas = [palavra for _, _, _, palavra in palavras_chave_resultados if palavra.lower() in pergunta.lower()]

        if palavras_encontradas:
            doc_ids_usados = set()
            resposta_output.delete('1.0', tk.END)
            resposta_output.insert(tk.END, f"🤖 Resposta baseada em palavras-chave:\n\nPalavras encontradas: {', '.join(palavras_encontradas)}\n\n")

            for doc_id, url, titulo, palavra in palavras_chave_resultados:
                if palavra.lower() in pergunta.lower() and doc_id not in doc_ids_usados:
                    doc_ids_usados.add(doc_id)
                    cursor.execute("""
                        SELECT paragrafo FROM bloqueio_v2.documento_paragrafo_embedding
                        WHERE documento_id = %s LIMIT 1
                    """, (doc_id,))
                    paragrafo_row = cursor.fetchone()
                    if paragrafo_row:
                        paragrafo = paragrafo_row[0]
                        resposta_humana = gerar_resposta_humana(pergunta, paragrafo)
                        resposta_output.insert(tk.END, f"📄 Documento: {titulo}\n{resposta_humana}\n🔗 {url}\n\n")
                        cache[chave_cache] = {
                            "resposta": resposta_humana,
                            "url": url,
                            "score": 1.0
                        }
                        with open(CACHE_FILE, "w", encoding="utf-8") as f:
                            json.dump(cache, f, indent=2, ensure_ascii=False)
            return

        emb_response = openai.Embedding.create(
            input=pergunta,
            model="text-embedding-ada-002"
        )
        emb_pergunta = emb_response['data'][0]['embedding']

        cursor.execute("""
            SELECT d.titulo, d.url_arquivo, e.paragrafo, e.embedding
            FROM bloqueio_v2.documento_paragrafo_embedding e
            JOIN bloqueio_v2.documento d ON d.documento_id = e.documento_id
            WHERE d.subcategoria_id = %s
        """, (subcategoria_id,))
        resultados = cursor.fetchall()

        melhor_score = -1
        melhor_paragrafo = ""
        melhor_url = ""

        for titulo, url, paragrafo, emb_db in resultados:
            try:
                emb_doc = json.loads(emb_db) if isinstance(emb_db, str) else emb_db
                score = cosine_similarity(emb_pergunta, emb_doc)
                if score > melhor_score:
                    melhor_score = score
                    melhor_paragrafo = paragrafo
                    melhor_url = url
            except Exception as parse_err:
                print(f"Erro ao processar embedding do parágrafo: {parse_err}")
                continue

        resposta_output.delete('1.0', tk.END)

        if melhor_score >= 0.85:
            resposta_humana = gerar_resposta_humana(pergunta, melhor_paragrafo)
            resposta_output.insert(tk.END, f"{resposta_humana}\n\n🔗 {melhor_url}\n📈 Similaridade: {melhor_score:.4f}")
            cache[chave_cache] = {
                "resposta": resposta_humana,
                "url": melhor_url,
                "score": melhor_score
            }
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
        else:
            resposta_output.insert(tk.END, "❌ Nenhuma resposta suficientemente relevante encontrada.")

            try:
                categoria_id = int(categoria_var.get().split(" - ")[0])
                script_path = os.environ.get("SECONDARY_AGENT_PATH", "salvar_pendencia_mistral.py")
                subprocess.Popen([
                    "python",
                    script_path,
                    pergunta,
                    str(categoria_id),
                    str(subcategoria_id),
                    "999"
                ])
                resposta_output.insert(tk.END, "\n📌 A pergunta foi enviada para análise por outro agente de IA.")
            except Exception as e:
                resposta_output.insert(tk.END, f"\n⚠️ Falha ao enviar para o agente secundário: {e}")

    except Exception as e:
        messagebox.showerror("Erro", str(e))

app = tk.Tk()
app.title("Atendimento com IA")
app.geometry("900x600")

tk.Label(app, text="Categoria:", font=("Arial", 12)).pack(pady=5)
categoria_var = tk.StringVar()
categoria_combo = ttk.Combobox(app, textvariable=categoria_var, width=50, state="readonly")
categoria_combo['values'] = [f"{id} - {nome}" for id, nome in carregar_categorias()]
categoria_combo.pack()
categoria_combo.bind("<<ComboboxSelected>>", carregar_subcategorias)

tk.Label(app, text="Subcategoria:", font=("Arial", 12)).pack(pady=5)
subcategoria_var = tk.StringVar()
subcategoria_combo = ttk.Combobox(app, textvariable=subcategoria_var, width=50, state="readonly")
subcategoria_combo.pack()

tk.Label(app, text="Digite sua pergunta:", font=("Arial", 12)).pack(pady=5)
pergunta_entry = tk.Entry(app, width=80, font=("Arial", 12))
pergunta_entry.pack(pady=5)

tk.Button(app, text="Buscar Resposta", font=("Arial", 12), bg="blue", fg="white", command=buscar_resposta).pack(pady=10)

resposta_output = tk.Text(app, wrap=tk.WORD, font=("Arial", 11), width=100, height=20)
resposta_output.pack(pady=10)

app.mainloop()
