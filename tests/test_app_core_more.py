import datetime
import json

import pandas as pd
import app_core as core


def setup_lab_with_insumos(tmp_path, monkeypatch):
    dbfile = tmp_path / "test_sistema.db"
    monkeypatch.setattr(core, "DB_NAME", str(dbfile))
    core.criar_tabelas()
    conn = core.conectar()
    c = conn.cursor()
    # cria um laboratório
    c.execute("INSERT INTO laboratorios (nome, capacidade, status_lab) VALUES (?, ?, ?)", ("Lab X", 20, "Ativo"))
    conn.commit()
    c.execute("SELECT id FROM laboratorios WHERE nome = ?", ("Lab X",))
    id_lab = c.fetchone()[0]
    return conn, id_lab


def test_processar_baixa_estoque_real(tmp_path, monkeypatch):
    conn, id_lab = setup_lab_with_insumos(tmp_path, monkeypatch)
    c = conn.cursor()
    # insere insumos
    c.execute(
        "INSERT INTO insumos (nome, categoria, quantidade, unidade, id_lab) VALUES (?, ?, ?, ?, ?)",
        ("Álcool", "Consumível", 10.0, "L", id_lab),
    )
    conn.commit()

    # cria agendamento com materiais JSON
    materiais = {"Álcool (L)": 2}
    c.execute(
        "INSERT INTO agendamentos (professor, disciplina, curso, qtd_alunos, id_lab, data, horario_inicio, horario_fim, status, roteiro, materiais) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "Prof",
            "Disc",
            "Curso",
            10,
            id_lab,
            str(datetime.date.today()),
            "08:00",
            "10:00",
            "RESERVADO",
            "",
            json.dumps(materiais, ensure_ascii=False),
        ),
    )
    conn.commit()
    c.execute("SELECT id FROM agendamentos ORDER BY id DESC LIMIT 1")
    ag_id = c.fetchone()[0]

    # processa baixa
    ok = core.processar_baixa_estoque_real(ag_id, {"Álcool (L)": 2})
    assert ok is True

    c.execute("SELECT quantidade FROM insumos WHERE nome = ? AND id_lab = ?", ("Álcool", id_lab))
    novo = float(c.fetchone()[0])
    assert novo == 8.0


def test_obter_detalhes_materiais_parsing(tmp_path, monkeypatch):
    conn, id_lab = setup_lab_with_insumos(tmp_path, monkeypatch)
    c = conn.cursor()
    # insumo para correspondência
    c.execute(
        "INSERT INTO insumos (nome, categoria, quantidade, unidade, id_lab) VALUES (?, ?, ?, ?, ?)",
        ("Microscópio", "Equipamento", 1, "un", id_lab),
    )
    conn.commit()

    materiais = {"Microscópio (un)": 1}
    c.execute(
        "INSERT INTO agendamentos (professor, disciplina, curso, qtd_alunos, id_lab, data, horario_inicio, horario_fim, status, roteiro, materiais) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "Prof",
            "Disc",
            "Curso",
            5,
            id_lab,
            str(datetime.date.today()),
            "09:00",
            "11:00",
            "SOLICITADO",
            "",
            json.dumps(materiais, ensure_ascii=False),
        ),
    )
    conn.commit()
    c.execute("SELECT id FROM agendamentos ORDER BY id DESC LIMIT 1")
    ag_id = c.fetchone()[0]

    detalhes = core.obter_detalhes_materiais(ag_id)
    assert isinstance(detalhes, list)
    assert detalhes[0]["Item"] == "Microscópio"


def test_verificar_conflito(tmp_path, monkeypatch):
    conn, id_lab = setup_lab_with_insumos(tmp_path, monkeypatch)
    c = conn.cursor()

    # cria um agendamento existente
    c.execute(
        "INSERT INTO agendamentos (professor, disciplina, curso, qtd_alunos, id_lab, data, horario_inicio, horario_fim, status, roteiro, materiais) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "Prof",
            "Disc",
            "Curso",
            5,
            id_lab,
            "2026-05-01",
            "10:00",
            "12:00",
            "RESERVADO",
            "",
            json.dumps({}, ensure_ascii=False),
        ),
    )
    conn.commit()

    # conflito: 11:00-13:00 sobrepõe
    assert core.verificar_conflito(id_lab, "2026-05-01", "11:00", "13:00") is True
    # não conflito: 08:00-09:00
    assert core.verificar_conflito(id_lab, "2026-05-01", "08:00", "09:00") is False
