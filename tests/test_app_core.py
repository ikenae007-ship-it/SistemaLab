import json
import app_core as core


def test_gerar_lista_horarios_length():
    lst = core.gerar_lista_horarios()
    # 08:00 até 22:00 a cada 30 minutos -> 29 entradas
    assert len(lst) == 29
    assert lst[0] == "08:00"
    assert lst[-1] == "22:00"


def test_password_hash_and_verify():
    pwd = "s3cr3t"
    saved = core._hash_password(pwd)
    assert core._verify_password(saved, pwd) is True
    assert core._verify_password(saved, pwd + "x") is False


def test_criar_e_contar_usuarios(tmp_path, monkeypatch):
    dbfile = tmp_path / "test_sistema.db"
    monkeypatch.setattr(core, "DB_NAME", str(dbfile))
    # cria esquema limpo
    core.criar_tabelas()
    assert core.contar_usuarios() == 0

    core.criar_usuario("prof@exemplo.test", "senha123", perfil="Professor")
    assert core.contar_usuarios() == 1

    assert core.verificar_credenciais("prof@exemplo.test", "senha123") is not None
    assert core.verificar_credenciais("prof@exemplo.test", "errada") is None
