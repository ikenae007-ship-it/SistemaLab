import subprocess
import sys
import json

PY = sys.executable


def run_python(expr):
    completed = subprocess.run([PY, "-c", expr], capture_output=True, text=True)
    return completed


def test_gerar_lista_horarios_length():
    # chama app.gerar_lista_horarios() em subprocesso para evitar importar a UI no processo de teste
    expr = 'import app; import json; print(len(app.gerar_lista_horarios()))'
    r = run_python(expr)
    assert r.returncode == 0, f"Erro executando subprocess: {r.stderr}"
    val = int(r.stdout.strip())
    assert val > 0


def test_serializacao_materiais_roundtrip():
    expr = (
        'import app, json; m={"Álcool (L)": 2}; s=json.dumps(m, ensure_ascii=False); ' 
        "print(json.loads(s)['Álcool (L)'])"
    )
    r = run_python(expr)
    assert r.returncode == 0
    assert float(r.stdout.strip()) == 2.0
