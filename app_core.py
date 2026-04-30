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

    conn.commit()
    conn.close()


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
