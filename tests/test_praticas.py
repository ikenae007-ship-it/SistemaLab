import json
import math
import app_core as core


def test_criar_e_calcular_pratica(tmp_path, monkeypatch):
    dbfile = tmp_path / "test_praticas.db"
    monkeypatch.setattr(core, "DB_NAME", str(dbfile))
    core.criar_tabelas()

    # criar laboratório com 6 bancadas, 4 alunos por bancada
    conn = core.conectar()
    c = conn.cursor()
    c.execute("INSERT INTO laboratorios (nome, bloco, capacidade, status_lab, bancadas, alunos_por_bancada) VALUES (?,?,?,?,?,?)",
              ("Lab A", "Bloco X", 24, "Ativo", 6, 4))
    id_lab = c.lastrowid
    conn.commit()
    conn.close()

    materiais = [
        {"nome": "Pipeta", "unidade": "un", "por": "aluno", "qtd_por_aluno": 1},
        {"nome": "Reagente X", "unidade": "mL", "por": "bancada", "qtd_por_bancada": 50},
    ]

    id_pr = core.criar_pratica("Química", "Tit1", "Teste", materiais)

    # 10 alunos -> 10 pipetas, bancadas necessárias = ceil(10/4)=3 -> 3*50 = 150 mL
    res = core.calcular_materiais_pratica(id_pr, id_lab, 10)
    # normalizar por nome
    byname = {r['nome']: r for r in res}
    assert byname['Pipeta']['quantidade_necessaria'] == 10
    assert byname['Reagente X']['quantidade_necessaria'] == 150

    # 25 alunos -> ceil(25/4)=7 bancadas
    res2 = core.calcular_materiais_pratica(id_pr, id_lab, 25)
    byname2 = {r['nome']: r for r in res2}
    assert byname2['Pipeta']['quantidade_necessaria'] == 25
    assert byname2['Reagente X']['quantidade_necessaria'] == 7 * 50
