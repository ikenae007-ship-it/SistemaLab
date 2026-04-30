import os
import datetime
import sqlite3
import ast
import json
import hashlib
import binascii
import hmac
import logging

import pandas as pd
import csv
import math
import io


# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


DB_NAME = "sistema_lab.db"


def conectar():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def criar_tabelas():
    conn = conectar()
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS laboratorios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            bloco TEXT,
            capacidade INTEGER,
            tecnico_responsavel TEXT,
            status_lab TEXT DEFAULT 'Ativo'
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS insumos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            categoria TEXT,
            quantidade REAL,
            unidade TEXT,
            estoque_minimo REAL,
            id_lab INTEGER,
            FOREIGN KEY (id_lab) REFERENCES laboratorios(id)
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS agendamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            professor TEXT,
            disciplina TEXT,
            curso TEXT,
            qtd_alunos INTEGER,
            id_lab INTEGER,
            data TEXT,
            horario_inicio TEXT,
            horario_fim TEXT,
            status TEXT,
            roteiro TEXT,
            materiais TEXT,
            FOREIGN KEY (id_lab) REFERENCES laboratorios(id)
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS equipe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cargo TEXT,
            id_lab_responsavel INTEGER,
            FOREIGN KEY (id_lab_responsavel) REFERENCES laboratorios(id)
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            perfil TEXT
        )
        """
    )

    # tabela de práticas (repositório de roteiros)
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS praticas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            disciplina TEXT,
            titulo TEXT,
            descricao TEXT,
            materiais TEXT,
            criado_em TEXT DEFAULT (date('now'))
        )
        """
    )

    conn.commit()
    # garantir colunas adicionais em laboratorios (migração suave)
    _ensure_lab_columns(conn)

    conn.close()


def _ensure_lab_columns(conn: sqlite3.Connection):
    # garante que as colunas `bancadas` e `alunos_por_bancada` existam
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(laboratorios)")
    cols = [r[1] for r in cur.fetchall()]
    if "bancadas" not in cols:
        cur.execute("ALTER TABLE laboratorios ADD COLUMN bancadas INTEGER DEFAULT 1")
    if "alunos_por_bancada" not in cols:
        cur.execute("ALTER TABLE laboratorios ADD COLUMN alunos_por_bancada INTEGER DEFAULT 1")
    conn.commit()


def verificar_conflito(id_lab, data, h_inicio, h_fim):
    conn = conectar()
    query = """
        SELECT horario_inicio, horario_fim
        FROM agendamentos
        WHERE id_lab = ? AND data = ? AND status != 'CANCELADO'
    """
    df = pd.read_sql_query(query, conn, params=(id_lab, data))
    conn.close()

    if df.empty:
        return False

    nova_ini = pd.to_datetime(h_inicio, format="%H:%M").time()
    nova_fim = pd.to_datetime(h_fim, format="%H:%M").time()

    for _, row in df.iterrows():
        exist_ini = pd.to_datetime(row["horario_inicio"], format="%H:%M").time()
        exist_fim = pd.to_datetime(row["horario_fim"], format="%H:%M").time()
        if nova_ini < exist_fim and nova_fim > exist_ini:
            return True

    return False


def obter_capacidade_labs_db():
    conn = conectar()
    try:
        df = pd.read_sql_query("SELECT nome, capacidade FROM laboratorios", conn)
        conn.close()
        if df.empty:
            return {"Lab Padrão": 30}
        return pd.Series(df.capacidade.values, index=df.nome).to_dict()
    except Exception:
        logger.exception("Erro ao obter capacidades dos labs")
        conn.close()
        return {"Lab Padrão": 30}


def gerar_lista_horarios():
    horarios = []
    inicio = datetime.time(8, 0)
    fim = datetime.time(22, 0)
    atual = datetime.datetime.combine(datetime.date.today(), inicio)
    limite = datetime.datetime.combine(datetime.date.today(), fim)
    while atual <= limite:
        horarios.append(atual.strftime("%H:%M"))
        atual += datetime.timedelta(minutes=30)
    return horarios


def verificar_disponibilidade(id_lab, data, h_inicio, h_fim):
    conn = conectar()
    c = conn.cursor()
    ini = h_inicio.strftime("%H:%M")
    fim = h_fim.strftime("%H:%M")
    query = """
        SELECT 1
        FROM agendamentos
        WHERE id_lab = ? AND data = ?
        AND (? < horario_fim AND ? > horario_inicio)
        AND status IN ('SOLICITADO', 'RESERVADO', 'OCUPADO')
    """
    c.execute(query, (id_lab, str(data), ini, fim))
    conflito = c.fetchone()
    conn.close()
    return conflito is None


# Autenticação simples


def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return binascii.hexlify(salt).decode() + "$" + binascii.hexlify(dk).decode()


def _verify_password(stored_hash: str, provided_password: str) -> bool:
    try:
        salt_hex, hash_hex = stored_hash.split("$")
        salt = binascii.unhexlify(salt_hex)
        expected = binascii.unhexlify(hash_hex)
        dk = hashlib.pbkdf2_hmac("sha256", provided_password.encode("utf-8"), salt, 100000)
        return hmac.compare_digest(dk, expected)
    except Exception:
        logger.exception("Erro ao verificar senha")
        return False


def criar_usuario(email: str, password: str, perfil: str = None):
    conn = conectar()
    c = conn.cursor()
    ph = _hash_password(password)
    try:
        c.execute(
            "INSERT OR REPLACE INTO usuarios (email, password_hash, perfil) VALUES (?, ?, ?)",
            (email, ph, perfil),
        )
        conn.commit()
    finally:
        conn.close()


def contar_usuarios() -> int:
    conn = conectar()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM usuarios")
    n = c.fetchone()[0]
    conn.close()
    return int(n)


def verificar_credenciais(email: str, password: str):
    conn = conectar()
    try:
        df = pd.read_sql_query("SELECT password_hash, perfil FROM usuarios WHERE email = ?", conn, params=(email,))
        if df.empty:
            return None
        stored = df.iloc[0]["password_hash"]
        perfil = df.iloc[0].get("perfil")
        if _verify_password(stored, password):
            return perfil
        return None
    finally:
        conn.close()


def salvar_agendamento(prof, disc, curso, qtd, id_lab, data, h_ini, h_fim, roteiro, materiais):
    with conectar() as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO agendamentos
                (professor, disciplina, curso, qtd_alunos, id_lab, data,
                horario_inicio, horario_fim, status, roteiro, materiais)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                prof,
                disc,
                curso,
                qtd,
                id_lab,
                str(data),
                h_ini.strftime("%H:%M"),
                h_fim.strftime("%H:%M"),
                "SOLICITADO",
                roteiro,
                json.dumps(materiais, ensure_ascii=False),
            ),
        )


def atualizar_status(id_pedido, novo_status):
    with conectar() as conn:
        c = conn.cursor()
        c.execute("UPDATE agendamentos SET status = ? WHERE id = ?", (novo_status, id_pedido))


def obter_detalhes_materiais(id_agendamento):
    conn = conectar()
    df = pd.read_sql_query(
        "SELECT materiais, id_lab FROM agendamentos WHERE id = ?",
        conn,
        params=(id_agendamento,),
    )
    conn.close()

    if df.empty:
        return []

    mats_raw = df.iloc[0]["materiais"]
    id_lab = df.iloc[0]["id_lab"]

    if not mats_raw:
        return []

    try:
        if isinstance(mats_raw, str):
            try:
                materias_obj = json.loads(mats_raw)
            except Exception:
                logger.exception("Falha ao fazer json.loads em materiais, tentando fallback")
                materias_obj = ast.literal_eval(mats_raw)
        else:
            materias_obj = mats_raw
    except Exception:
        logger.exception("Erro ao interpretar materiais do agendamento")
        return []

    if not isinstance(materias_obj, dict):
        return []

    conn = conectar()
    df_insumos = pd.read_sql_query(
        "SELECT nome, categoria, unidade FROM insumos WHERE id_lab = ?",
        conn,
        params=(id_lab,),
    )
    conn.close()

    todos_itens = []

    for item_com_unid, qtd in materias_obj.items():
        nome_exibicao = str(item_com_unid)
        nome_puro = nome_exibicao.split(" (")[0].strip()

        categoria = "Desconhecido"
        unidade = "un"

        if not df_insumos.empty:
            linha = df_insumos[df_insumos["nome"] == nome_puro]
            if linha.empty:
                linha = df_insumos[df_insumos["nome"].str.contains(nome_puro, case=False, na=False)]

            if not linha.empty:
                categoria = linha.iloc[0]["categoria"] or categoria
                unidade = linha.iloc[0]["unidade"] or unidade

        todos_itens.append(
            {
                "Item": nome_puro,
                "Qtd Pedida": qtd,
                "Unidade": unidade,
                "Categoria": categoria,
                "nome_exibicao": nome_exibicao,
            }
        )

    return todos_itens


def criar_pratica(disciplina: str, titulo: str, descricao: str, materiais: list):
    """Grava uma prática (materiais é uma lista de dicts conforme schema)."""
    with conectar() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO praticas (disciplina, titulo, descricao, materiais) VALUES (?,?,?,?)",
            (disciplina, titulo, descricao, json.dumps(materiais, ensure_ascii=False)),
        )
        return c.lastrowid


def listar_praticas():
    conn = conectar()
    df = pd.read_sql_query("SELECT id, disciplina, titulo, criado_em FROM praticas ORDER BY criado_em DESC", conn)
    conn.close()
    return df.to_dict(orient="records")


def obter_pratica(id_pratica: int):
    conn = conectar()
    df = pd.read_sql_query("SELECT * FROM praticas WHERE id = ?", conn, params=(id_pratica,))
    conn.close()
    if df.empty:
        return None
    row = df.iloc[0].to_dict()
    try:
        row["materiais"] = json.loads(row["materiais"]) if row.get("materiais") else []
    except Exception:
        try:
            row["materiais"] = ast.literal_eval(row.get("materiais") or "[]")
        except Exception:
            row["materiais"] = []
    return row


def importar_praticas_arquivo(file_bytes: bytes, filename: str = None):
    """Importa práticas a partir de JSON (array) ou CSV (linhas por material).
    Retorna número de práticas importadas."""
    text = None
    if isinstance(file_bytes, bytes):
        try:
            text = file_bytes.decode("utf-8")
        except Exception:
            text = file_bytes.decode("latin-1")
    else:
        text = str(file_bytes)

    name = (filename or "").lower()
    imported = 0
    if name.endswith(".json") or text.strip().startswith("["):
        data = json.loads(text)
        for p in data:
            materiais = p.get("materiais") or []
            criar_pratica(p.get("disciplina"), p.get("titulo"), p.get("descricao", ""), materiais)
            imported += 1
        return imported

    # CSV: agrupar por disciplina+titulo
    f = io.StringIO(text)
    reader = csv.DictReader(f)
    grupos = {}
    for r in reader:
        key = (r.get("disciplina"), r.get("titulo"))
        if key not in grupos:
            grupos[key] = {"disciplina": r.get("disciplina"), "titulo": r.get("titulo"), "descricao": r.get("descricao", ""), "materiais": []}
        mat = {
            "nome": r.get("material_nome"),
            "unidade": r.get("material_unidade") or "un",
            "por": r.get("por") or "aluno",
        }
        try:
            if r.get("qtd_por_aluno"):
                mat["qtd_por_aluno"] = float(r.get("qtd_por_aluno"))
        except Exception:
            pass
        try:
            if r.get("qtd_por_bancada"):
                mat["qtd_por_bancada"] = float(r.get("qtd_por_bancada"))
        except Exception:
            pass
        grupos[key]["materiais"].append(mat)

    for key, payload in grupos.items():
        criar_pratica(payload.get("disciplina"), payload.get("titulo"), payload.get("descricao"), payload.get("materiais"))
        imported += 1
    return imported


def calcular_materiais_pratica(pratica_id: int, id_lab: int, qtd_alunos: int, metodo_preferido: str = None):
    """Calcula quantidades necessárias para uma prática no lab informado.
    Retorna lista de dicts: nome, unidade, quantidade_necessaria, por.
    """
    pratica = obter_pratica(pratica_id)
    if not pratica:
        raise ValueError("Prática não encontrada")

    materiais = pratica.get("materiais") or []

    conn = conectar()
    df = pd.read_sql_query("SELECT capacidade, bancadas, alunos_por_bancada FROM laboratorios WHERE id = ?", conn, params=(id_lab,))
    conn.close()

    if df.empty:
        # fallback razoável
        capacidade = None
        bancadas = 1
        alunos_por_bancada = 1
    else:
        row = df.iloc[0]
        capacidade = int(row["capacidade"]) if pd.notna(row.get("capacidade")) else None
        bancadas = int(row.get("bancadas") or 1)
        alunos_por_bancada = int(row.get("alunos_por_bancada") or (capacidade // max(1, bancadas) if capacidade else 1))

    resultado = []
    for m in materiais:
        nome = m.get("nome")
        unidade = m.get("unidade") or "un"
        por = m.get("por") or "aluno"
        qtd = 0.0

        if por == "bancada":
            apb = int(m.get("alunos_por_bancada") or alunos_por_bancada or 1)
            num_bancadas = math.ceil(qtd_alunos / max(1, apb))
            qtd_por_bancada = float(m.get("qtd_por_bancada") or m.get("qtd_por_bancada", 1))
            qtd = num_bancadas * qtd_por_bancada
        else:
            qtd_por_aluno = float(m.get("qtd_por_aluno") or m.get("qtd_por_bancada") or 1)
            qtd = qtd_alunos * qtd_por_aluno

        resultado.append({"nome": nome, "unidade": unidade, "quantidade_necessaria": qtd, "por": por})

    return resultado


def processar_baixa_estoque_real(id_agendamento, materiais_usados):
    try:
        with conectar() as conn:
            c = conn.cursor()
            conn.execute("BEGIN IMMEDIATE")
            c.execute("SELECT id_lab, materiais FROM agendamentos WHERE id = ?", (id_agendamento,))
            row = c.fetchone()
            if not row:
                raise ValueError("Agendamento não encontrado")

            id_lab = row[0]

            for item, qtd_real in materiais_usados.items():
                nome_puro = item.split(" (")[0]
                c.execute(
                    "SELECT quantidade FROM insumos WHERE nome = ? AND id_lab = ?",
                    (nome_puro, id_lab),
                )
                r = c.fetchone()
                if r is None:
                    continue
                try:
                    atual = float(r[0]) if r[0] is not None else 0.0
                except Exception:
                    logger.exception("Falha ao converter quantidade atual para float")
                    atual = 0.0

                novo = max(0.0, atual - float(qtd_real))
                c.execute(
                    "UPDATE insumos SET quantidade = ? WHERE nome = ? AND id_lab = ?",
                    (novo, nome_puro, id_lab),
                )
            return True
    except Exception:
        logger.exception("Erro ao processar baixa de estoque")
        # Não acessar UI aqui; retornar False para que a camada de UI trate a mensagem
        return False
        return False
