# Sistema de Gestão de Laboratórios

Instruções rápidas:

1. Instale dependências:

```bash
pip install -r requirements.txt
```

2. Rodar a aplicação:

```bash
streamlit run app.py
```

3. Rodar testes:

```bash
pytest -q
```

Notas:
- Os testes chamam partes do `app.py` via subprocesso para evitar carregar a UI dentro do processo de teste.
- Recomenda-se revisar e isolar lógica em módulos (`db.py`, `auth.py`, `ui.py`) para testes mais robustos.
