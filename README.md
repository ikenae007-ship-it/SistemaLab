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

## Repositório de Práticas (novo)

Agora a aplicação possui um repositório de práticas com import CSV/JSON e cálculo automático de materiais.

Veja `templates/praticas_template.csv` como exemplo de importação. O README contém instruções rápidas:

- Faça login como `Coordenador`.
- No `Home` clique em `Repositório de Práticas`.
- Use `Importar práticas` para enviar CSV/JSON em lote.
- Selecione uma prática, escolha o laboratório e informe a quantidade de alunos.
- Pressione `Calcular materiais` para ver as quantidades necessárias e compará-las com o estoque do laboratório.

Migração: as colunas `bancadas` e `alunos_por_bancada` serão criadas automaticamente na tabela `laboratorios` caso não existam.
