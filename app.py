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
import streamlit as st


# ============================================================
# CONEXÃO E SCHEMA UNIFICADO
# ============================================================

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# ============================================================
# INICIALIZAÇÃO DO ESTADO DA SESSÃO
# ============================================================

if "logado" not in st.session_state:
    st.session_state.logado = False
if "perfil" not in st.session_state:
    st.session_state.perfil = None
if "usuario" not in st.session_state:
    st.session_state.usuario = ""
if "pagina" not in st.session_state:
    st.session_state.pagina = "home"

# ============================================================
# Externalize helpers into app_core for separation of concerns
import app_core as core

# Backwards-compatible re-exports for external callers/tests
gerar_lista_horarios = core.gerar_lista_horarios
contar_usuarios = core.contar_usuarios
criar_usuario = core.criar_usuario
verificar_credenciais = core.verificar_credenciais
verificar_conflito = core.verificar_conflito
salvar_agendamento = core.salvar_agendamento
obter_detalhes_materiais = core.obter_detalhes_materiais
atualizar_status = core.atualizar_status
processar_baixa_estoque_real = core.processar_baixa_estoque_real
obter_capacidade_labs_db = core.obter_capacidade_labs_db


# ============================================================
# PÁGINAS / INTERFACE
# ============================================================


def pagina_gestao_unidades():
    st.header("🏢 Mapa de Gestão de Laboratórios")

    conn = core.conectar()
    df_labs = pd.read_sql_query("SELECT * FROM laboratorios", conn)

    if df_labs.empty:
        st.warning("Nenhum laboratório cadastrado. Vá em 'Configurações' para adicionar o primeiro.")
        if st.button("➕ Cadastrar Novo Laboratório"):
            pass
        conn.close()
        return

    opcoes_labs = {row["nome"]: row["id"] for _, row in df_labs.iterrows()}
    nome_selecionado = st.selectbox(
        "Selecione a Unidade para Gerenciar:",
        ["-- Selecione --"] + list(opcoes_labs.keys()),
    )

    if nome_selecionado != "-- Selecione --":
        id_atual = opcoes_labs[nome_selecionado]

        tab_geral, tab_inventario, tab_agenda, tab_docs = st.tabs(
            [
                "📋 Dados Gerais",
                "📦 Inventário",
                "📅 Agenda da Unidade",
                "📄 Documentos/POPs",
            ]
        )

        with tab_geral:
            st.subheader(f"Informações Técnicas: {nome_selecionado}")
            # Implementar dados técnicos

        with tab_inventario:
            st.subheader(f"Estoque Exclusivo: {nome_selecionado}")
            # Implementar inventário

    else:
        st.info("💡 Escolha um laboratório acima para acessar o painel de controle detalhado.")

    conn.close()


# Inicialização das tabelas/schemas
# Inicializa tabelas via core
core.criar_tabelas()

# (Reinicialização de estado - guardado por compatibilidade)
if "logado" not in st.session_state:
    st.session_state.logado = False
if "perfil" not in st.session_state:
    st.session_state.perfil = None
if "usuario" not in st.session_state:
    st.session_state.usuario = ""

# ============================================================
# LOGIN
# ============================================================

if not st.session_state.logado:
    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        st.image(
            "https://images.seeklogo.com/logo-png/14/1/ucb-universidade-catolica-de-brasilia-logo-png_seeklogo-144022.png",
            use_column_width=True,
        )
        st.subheader("🔐 Portal de Gestão de Laboratórios")

        with st.form("login_form"):
            user = st.text_input("E-mail Institucional", placeholder="exemplo@ucb.com")
            password = st.text_input("Senha", type="password", placeholder="••••••••")
            tipo = st.selectbox("Acessar como:", ["Professor", "Técnico", "Coordenador"])

            if st.form_submit_button("Entrar no Sistema", use_container_width=True):
                if not user:
                    st.error("Por favor, insira seu e-mail.")
                else:
                    # Se não há usuários no sistema, o primeiro usuário criado é registrado automaticamente
                    total = core.contar_usuarios()
                    if total == 0:
                        # cria usuário inicial
                        core.criar_usuario(user, password or "", tipo)
                        st.success("Primeira conta criada. Você foi autenticado.")
                        st.session_state.logado = True
                        st.session_state.perfil = tipo
                        st.session_state.usuario = user
                        st.rerun()
                    else:
                        perfil_ok = core.verificar_credenciais(user, password or "")
                        if perfil_ok is not None:
                            st.session_state.logado = True
                            # usa o perfil armazenado (se houver), caso contrário usa seleção do form
                            st.session_state.perfil = perfil_ok or tipo
                            st.session_state.usuario = user
                            st.rerun()
                        else:
                            st.error("Credenciais inválidas. Verifique e tente novamente.")

else:
    perfil = st.session_state.perfil

    c_user, c_out = st.columns([4, 1])
    c_user.markdown(f"👋 Olá, **{st.session_state.usuario}**! ({perfil})")

    if st.session_state.pagina != "home":
        if c_out.button("🏠 Home", use_container_width=True):
            st.session_state.pagina = "home"
            st.rerun()
    else:
        if c_out.button("🚪 Sair", use_container_width=True):
            st.session_state.logado = False
            st.rerun()

    st.divider()

    # ========================================================
    # NAVEGAÇÃO PRINCIPAL
    # ========================================================
    if st.session_state.pagina == "home":
        st.title(f"Painel do {perfil}")
        if perfil == "Coordenador":
            if st.button("Abrir Gestão Geral", use_container_width=True):
                st.session_state.pagina = "gestao_coordenador"
                st.rerun()
            if st.button("Repositório de Práticas", use_container_width=True):
                st.session_state.pagina = "repo_praticas"
                st.rerun()

        elif perfil == "Professor":
            with st.container(border=True):
                st.subheader("Nova Solicitação")
                if st.button("Solicitar Laboratório", use_container_width=True):
                    st.session_state.pagina = "nova_aula"
                    st.rerun()

        elif perfil == "Técnico":
            with st.container(border=True):
                st.subheader("🛠️ Operação")
                if st.button("Abrir Painel Técnico", use_container_width=True):
                    st.session_state.pagina = "painel_tecnico"
                    st.rerun()

    # ========================================================
    # PÁGINA NOVA AULA (PROFESSOR)
    # ========================================================
    elif st.session_state.pagina == "nova_aula":
        st.header("📝 Nova Solicitação de Aula")

        conn = core.conectar()
        df_labs_info = pd.read_sql_query(
            "SELECT id, nome FROM laboratorios WHERE status_lab = 'Ativo'", conn
        )
        conn.close()

        dict_labs = {row["nome"]: row["id"] for _, row in df_labs_info.iterrows()}
        opcoes_labs = ["-- Selecione --"] + list(dict_labs.keys())

        lab_selecionado = st.selectbox("Selecione o laboratório", options=opcoes_labs)

        if lab_selecionado != "-- Selecione --":
            id_lab_atual = dict_labs[lab_selecionado]

            conn = core.conectar()
            cap_query = pd.read_sql_query(
                "SELECT capacidade FROM laboratorios WHERE id = ?",
                conn,
                params=(id_lab_atual,),
            )
            conn.close()

            lotacao_max_raw = cap_query.iloc[0]["capacidade"] if not cap_query.empty else 0
            try:
                lotacao_max = int(lotacao_max_raw)
            except (TypeError, ValueError):
                lotacao_max = 0

            st.info(f"📍 **Lotação Máxima do {lab_selecionado}:** {lotacao_max} alunos")

            conn = core.conectar()
            query_ocupados = """
                SELECT data, horario_inicio, horario_fim, professor
                FROM agendamentos
                WHERE id_lab = ? AND data >= ? AND status != 'RECUSADO'
            """
            df_ocupados = pd.read_sql_query(
                query_ocupados,
                conn,
                params=(id_lab_atual, str(datetime.date.today())),
            )
            conn.close()

            if not df_ocupados.empty:
                st.subheader("📅 Horários Ocupados")
                st.dataframe(df_ocupados, use_container_width=True, hide_index=True)

            if "ids_linhas" not in st.session_state:
                st.session_state.ids_linhas = {"cons": [0], "ncons": [0], "equip": [0]}

            nome = st.text_input(
                "Nome do Professor", value=st.session_state.get("usuario", "")
            )
            c1, c2 = st.columns(2)
            with c1:
                disciplina = st.text_input("Nome da Disciplina")
                curso = st.selectbox(
                    "Curso",
                    [
                        "Biomedicina",
                        "Farmácia",
                        "Enfermagem",
                        "Nutrição",
                        "Fisioterapia",
                    ],
                )
            with c2:
                cap_max_input = lotacao_max if lotacao_max > 0 else 1
                qtd_alunos = st.number_input(
                    "Quantidade de Alunos",
                    min_value=1,
                    max_value=cap_max_input,
                    step=1,
                )
                dt = st.date_input("Data da Aula")

            lista_h = core.gerar_lista_horarios()
            h_ini_str = st.selectbox("Início", options=lista_h, index=21)
            h_fim_str = st.selectbox("Término", options=lista_h, index=25)

            h_ini = datetime.datetime.strptime(h_ini_str, "%H:%M").time()
            h_fim = datetime.datetime.strptime(h_fim_str, "%H:%M").time()

            st.subheader("📦 Materiais e Equipamentos")
            materiais_selecionados = {}

            conn = core.conectar()
            df_estoque = pd.read_sql_query(
                "SELECT nome, categoria, quantidade, unidade FROM insumos WHERE id_lab = ?",
                conn,
                params=(id_lab_atual,),
            )
            conn.close()

            tabs_mats = st.tabs(["💧 Consumíveis", "🧪 Não Consumíveis", "🔬 Equipamentos"])
            cats = {
                "cons": ("Consumível", tabs_mats[0]),
                "ncons": ("Não Consumível", tabs_mats[1]),
                "equip": ("Equipamento", tabs_mats[2]),
            }

            for pref, (label, aba) in cats.items():
                with aba:
                    itens_cat = df_estoque[df_estoque["categoria"] == label]
                    if itens_cat.empty:
                        st.warning(f"Sem {label} para este laboratório.")
                    else:
                        for i in st.session_state.ids_linhas[pref]:
                            col_sel, col_q, col_uni, col_del = st.columns(
                                [3, 0.8, 0.7, 0.5]
                            )
                            opcoes_itens = ["-- Selecione --"] + itens_cat["nome"].tolist()
                            sel = col_sel.selectbox(
                                f"Item {i}",
                                opcoes_itens,
                                key=f"s_{pref}_{i}",
                                label_visibility="collapsed",
                            )

                            if sel != "-- Selecione --":
                                item_info = itens_cat[itens_cat["nome"] == sel].iloc[0]
                                max_v = float(item_info["quantidade"])
                                unid_texto = (
                                    item_info["unidade"]
                                    if pd.notna(item_info["unidade"])
                                    else "un"
                                )

                                q = col_q.number_input(
                                    "Qtd",
                                    0.0,
                                    max_v,
                                    key=f"q_{pref}_{i}",
                                    label_visibility="collapsed",
                                )
                                col_uni.markdown(
                                    f"<p style='margin-top:5px; color:gray;'>{unid_texto}</p>",
                                    unsafe_allow_html=True,
                                )

                                if q > 0:
                                    materiais_selecionados[f"{sel} ({unid_texto})"] = q

                            if col_del.button("🗑️", key=f"d_{pref}_{i}"):
                                st.session_state.ids_linhas[pref].remove(i)
                                st.rerun()

                        if st.button(f"➕ Adicionar {label}", key=f"b_{pref}"):
                            st.session_state.ids_linhas[pref].append(
                                max(st.session_state.ids_linhas[pref] + [0]) + 1
                            )
                            st.rerun()

            st.write("---")
            obs = st.text_area("Roteiro detalhado / Observações")

            if st.button("🚀 Finalizar Solicitação", use_container_width=True):
                if not nome or not disciplina:
                    st.error("Preencha o Nome do Professor e a Disciplina!")
                elif lotacao_max and qtd_alunos > lotacao_max:
                    st.error(
                        f"A quantidade de alunos excede a capacidade do laboratório ({lotacao_max})!"
                    )
                else:
                    data_str = dt.strftime("%Y-%m-%d")
                    if core.verificar_conflito(id_lab_atual, data_str, h_ini_str, h_fim_str):
                        st.error(
                            "❌ Conflito de Horário: Já existe uma aula neste laboratório neste horário."
                        )
                    else:
                        core.salvar_agendamento(
                            nome,
                            disciplina,
                            curso,
                            qtd_alunos,
                            id_lab_atual,
                            dt,
                            h_ini,
                            h_fim,
                            obs,
                            materiais_selecionados,
                        )

                        st.success("✅ Solicitação enviada com sucesso!")
                        st.balloons()
                        st.session_state.ids_linhas = {
                            "cons": [0],
                            "ncons": [0],
                            "equip": [0],
                        }

                        st.session_state.pagina = "home"
                        st.rerun()

    # ========================================================
    # REPOSITÓRIO DE PRÁTICAS
    # ========================================================
    elif st.session_state.pagina == "repo_praticas":
        st.header("📚 Repositório de Práticas")

        col_u, col_v = st.columns([3, 1])
        with col_u:
            st.subheader("Práticas Cadastradas")
            praticas = core.listar_praticas()
            if praticas:
                df_pr = pd.DataFrame(praticas)
                st.dataframe(df_pr, use_container_width=True, hide_index=True)
                sel = st.selectbox("Escolha uma prática para ver detalhes:", ["-- Nenhuma --"] + [f"{p['id']} - {p['titulo']} ({p['disciplina']})" for p in praticas])
            else:
                st.info("Nenhuma prática cadastrada ainda.")
                sel = "-- Nenhuma --"

        with col_v:
            if st.button("Voltar", use_container_width=True):
                st.session_state.pagina = "home"
                st.rerun()

        # Formulário para criar nova prática (editor com linhas dinâmicas)
        st.subheader("Criar nova prática")
        if "praticas_rows" not in st.session_state:
            st.session_state.praticas_rows = [0]

        with st.form("form_nova_pratica"):
            col_a, col_b = st.columns(2)
            with col_a:
                nova_disc = st.text_input("Disciplina")
                novo_tit = st.text_input("Título da prática")
            with col_b:
                nova_desc = st.text_area("Descrição", height=80)

            st.markdown("**Materiais (adicione linhas conforme necessário)**")
            to_delete = None
            for i in st.session_state.praticas_rows:
                cols = st.columns([3, 1, 1, 1, 0.5])
                nome = cols[0].text_input("Nome do material", key=f"mat_nome_{i}")
                unidade = cols[1].text_input("Unidade", value="un", key=f"mat_un_{i}")
                por = cols[2].selectbox("Por", ["aluno", "bancada"], key=f"mat_por_{i}")
                q_al = cols[3].number_input("Qtd/Aluno", min_value=0.0, value=0.0, key=f"mat_qal_{i}")
                if cols[4].button("🗑️", key=f"mat_del_{i}"):
                    to_delete = i

            if to_delete is not None:
                st.session_state.praticas_rows.remove(to_delete)
                st.experimental_rerun()

            col_add, col_submit = st.columns([1, 1])
            if col_add.button("➕ Adicionar material"):
                st.session_state.praticas_rows.append(max(st.session_state.praticas_rows + [0]) + 1)
                st.experimental_rerun()

            if col_submit.form_submit_button("Salvar Prática"):
                # coletar materiais
                mats = []
                for i in st.session_state.praticas_rows:
                    nome = st.session_state.get(f"mat_nome_{i}", "").strip()
                    if not nome:
                        continue
                    unidade = st.session_state.get(f"mat_un_{i}", "un")
                    por = st.session_state.get(f"mat_por_{i}", "aluno")
                    q_al = st.session_state.get(f"mat_qal_{i}", 0.0)
                    mat = {"nome": nome, "unidade": unidade, "por": por}
                    if por == "aluno":
                        mat["qtd_por_aluno"] = float(q_al)
                    else:
                        mat["qtd_por_bancada"] = float(q_al)
                    mats.append(mat)

                if not nova_disc or not novo_tit:
                    st.error("Disciplina e Título são obrigatórios.")
                elif not mats:
                    st.error("Adicione ao menos um material para a prática.")
                else:
                    try:
                        core.criar_pratica(nova_disc, novo_tit, nova_desc or "", mats)
                        st.success("Prática criada com sucesso.")
                        # resetar campos
                        st.session_state.praticas_rows = [0]
                        for k in list(st.session_state.keys()):
                            if str(k).startswith("mat_"):
                                del st.session_state[k]
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Falha ao salvar prática: {e}")

        st.divider()

        # Upload de arquivos (CSV/JSON)
        st.subheader("Importar práticas (CSV / JSON)")
        uploaded = st.file_uploader("Escolha um arquivo .csv ou .json", type=["csv", "json"])
        if uploaded is not None:
            content = uploaded.getvalue()
            # Validação básica antes de importar
            try:
                name_l = (uploaded.name or "").lower()
                text = None
                try:
                    text = content.decode("utf-8")
                except Exception:
                    text = content.decode("latin-1")

                valid = True
                errors = []
                if name_l.endswith(".json") or text.strip().startswith("["):
                    try:
                        parsed = json.loads(text)
                        if not isinstance(parsed, list):
                            valid = False
                            errors.append("JSON deve ser um array de práticas.")
                        else:
                            for idx, p in enumerate(parsed):
                                if not p.get("disciplina") or not p.get("titulo"):
                                    valid = False
                                    errors.append(f"Prática no índice {idx} precisa de 'disciplina' e 'titulo'.")
                                mats = p.get("materiais") or []
                                if not isinstance(mats, list) or any(not m.get("nome") for m in mats):
                                    valid = False
                                    errors.append(f"Prática no índice {idx} tem materiais inválidos (cada material precisa de 'nome').")
                    except Exception as e:
                        valid = False
                        errors.append(f"JSON inválido: {e}")
                else:
                    # CSV: validar cabeçalhos mínimos
                    import csv as _csv, io as _io

                    f = _io.StringIO(text)
                    try:
                        reader = _csv.DictReader(f)
                        headers = reader.fieldnames or []
                        needed = ["disciplina", "titulo", "material_nome"]
                        for h in needed:
                            if h not in headers:
                                valid = False
                                errors.append(f"CSV faltando coluna obrigatória: {h}")
                                break
                    except Exception as e:
                        valid = False
                        errors.append(f"CSV inválido: {e}")

                if not valid:
                    for e in errors:
                        st.error(e)
                else:
                    n = core.importar_praticas_arquivo(content, uploaded.name)
                    st.success(f"Importadas {n} práticas com sucesso.")
            except Exception as e:
                st.error(f"Falha ao importar: {e}")

        st.divider()

        # Visualizar prática selecionada
        if sel != "-- Nenhuma --":
            pid = int(sel.split(" - ")[0])
            p = core.obter_pratica(pid)
            if p:
                st.subheader(f"{p['titulo']} — {p['disciplina']}")
                st.write(p.get("descricao", ""))
                st.markdown("**Materiais (lista):**")
                st.write(p.get("materiais", []))

                # Expander para edição da prática
                with st.expander("✏️ Editar prática"):
                    if "edit_rows" not in st.session_state:
                        st.session_state.edit_rows = [i for i, _ in enumerate(p.get("materiais", []) or [0])]

                    with st.form(f"form_edit_pratica_{pid}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            e_disc = st.text_input("Disciplina", value=p.get("disciplina") or "")
                            e_tit = st.text_input("Título", value=p.get("titulo") or "")
                        with col2:
                            e_desc = st.text_area("Descrição", value=p.get("descricao") or "", height=80)

                        # materiais editáveis
                        to_del = None
                        for i in st.session_state.edit_rows:
                            mat = (p.get("materiais") or [])[i] if i < len(p.get("materiais") or []) else {}
                            cols = st.columns([3, 1, 1, 1, 0.5])
                            name_m = cols[0].text_input("Nome", value=mat.get("nome", ""), key=f"e_mat_nome_{pid}_{i}")
                            unit_m = cols[1].text_input("Unidade", value=mat.get("unidade", "un"), key=f"e_mat_un_{pid}_{i}")
                            por_m = cols[2].selectbox("Por", ["aluno", "bancada"], index=0 if mat.get("por","aluno")=="aluno" else 1, key=f"e_mat_por_{pid}_{i}")
                            q_m = cols[3].number_input("Qtd", min_value=0.0, value=float(mat.get("qtd_por_aluno") or mat.get("qtd_por_bancada") or 0.0), key=f"e_mat_q_{pid}_{i}")
                            if cols[4].button("🗑️", key=f"e_mat_del_{pid}_{i}"):
                                to_del = i

                        if to_del is not None:
                            st.session_state.edit_rows.remove(to_del)
                            st.experimental_rerun()

                        col_a, col_b = st.columns([1, 1])
                        if col_a.button("➕ Adicionar material (edição)"):
                            st.session_state.edit_rows.append(max(st.session_state.edit_rows + [0]) + 1)
                            st.experimental_rerun()

                        if col_b.form_submit_button("Salvar alterações"):
                            # coletar materiais editados
                            mats_edit = []
                            for i in st.session_state.edit_rows:
                                nm = st.session_state.get(f"e_mat_nome_{pid}_{i}", "").strip()
                                if not nm:
                                    continue
                                un = st.session_state.get(f"e_mat_un_{pid}_{i}", "un")
                                porv = st.session_state.get(f"e_mat_por_{pid}_{i}", "aluno")
                                qv = float(st.session_state.get(f"e_mat_q_{pid}_{i}", 0.0) or 0.0)
                                mobj = {"nome": nm, "unidade": un, "por": porv}
                                if porv == "aluno":
                                    mobj["qtd_por_aluno"] = qv
                                else:
                                    mobj["qtd_por_bancada"] = qv
                                mats_edit.append(mobj)

                            try:
                                updated = core.atualizar_pratica(pid, e_disc, e_tit, e_desc or "", mats_edit)
                                if updated:
                                    st.success("Prática atualizada com sucesso.")
                                    # limpar estados temporários
                                    for k in list(st.session_state.keys()):
                                        if str(k).startswith(f"e_mat_"):
                                            del st.session_state[k]
                                    del st.session_state["edit_rows"]
                                    st.experimental_rerun()
                                else:
                                    st.error("Falha ao atualizar (registro não encontrado).")
                            except Exception as e:
                                st.error(f"Erro ao atualizar: {e}")

                st.markdown("---")
                st.subheader("Calcular materiais para um laboratório")
                conn = core.conectar()
                df_labs = pd.read_sql_query("SELECT id, nome FROM laboratorios WHERE status_lab = 'Ativo'", conn)
                conn.close()
                if df_labs.empty:
                    st.warning("Nenhum laboratório ativo cadastrado.")
                else:
                    lab_opts = {row['nome']: row['id'] for _, row in df_labs.iterrows()}
                    lab_sel = st.selectbox("Escolha o laboratório:", ["-- Selecione --"] + list(lab_opts.keys()))
                    qtd_alunos = st.number_input("Quantidade de alunos", min_value=1, value=1)
                    if lab_sel != "-- Selecione --":
                        if st.button("Calcular materiais", use_container_width=True):
                            id_lab_calc = lab_opts[lab_sel]
                            try:
                                resultado = core.calcular_materiais_pratica(pid, id_lab_calc, int(qtd_alunos))
                                df_res = pd.DataFrame(resultado)
                                # comparar com estoque
                                conn = core.conectar()
                                df_stock = pd.read_sql_query("SELECT nome, quantidade, unidade FROM insumos WHERE id_lab = ?", conn, params=(id_lab_calc,))
                                conn.close()
                                if not df_stock.empty:
                                    df_res = df_res.merge(df_stock, left_on='nome', right_on='nome', how='left', suffixes=("", "_estoque"))
                                st.dataframe(df_res[['nome','quantidade_necessaria','unidade','quantidade']], use_container_width=True)
                            except Exception as e:
                                st.error(f"Erro ao calcular: {e}")

        st.write("\n")

    # ========================================================
    # PÁGINA COORDENADOR
    # ========================================================
    elif perfil == "Coordenador":
        st.title("🏛️ Central de Coordenação")

        if "submenu_coord" not in st.session_state:
            st.session_state.submenu_coord = "Operacional"

        col1, col2 = st.columns(2)

        with col1:
            border_op = bool(st.session_state.submenu_coord == "Operacional")
            with st.container(border=border_op):
                st.subheader("🔔 Operacional")
                st.caption("Aprovação de aulas e controle de agenda")
                if st.button("Acessar Painel Operacional", use_container_width=True, key="btn_op"):
                    st.session_state.submenu_coord = "Operacional"
                    st.rerun()

        with col2:
            border_infra = bool(st.session_state.submenu_coord == "Infraestrutura")
            with st.container(border=border_infra):
                st.subheader("🏢 Infraestrutura")
                st.caption("Gestão de laboratórios e inventário")
                if st.button("Acessar Painel de Infra", use_container_width=True, key="btn_infra"):
                    st.session_state.submenu_coord = "Infraestrutura"
                    st.rerun()

        st.divider()

        if st.session_state.submenu_coord == "Operacional":
            tab_aprovacoes, tab_historico, tab_calendario = st.tabs(
                ["🔔 Aprovações Pendentes", "✅ Aulas Realizadas", "📅 Agenda Geral"]
            )

            with tab_aprovacoes:
                st.subheader("Solicitações aguardando aprovação")
                conn = core.conectar()
                query_p = """
                    SELECT a.*, l.nome AS nome_lab
                    FROM agendamentos a
                    JOIN laboratorios l ON a.id_lab = l.id
                    WHERE a.status = 'SOLICITADO'
                    ORDER BY a.data ASC
                """
                df_pendente = pd.read_sql_query(query_p, conn)
                conn.close()

                if df_pendente.empty:
                    st.success("Não há aulas aguardando aprovação.")
                else:
                    for _, row in df_pendente.iterrows():
                        with st.container(border=True):
                            c1, c2 = st.columns([3, 1])
                            with c1:
                                st.markdown(
                                    f"**🔬 {row['nome_lab']}** | 📅 {row['data']} "
                                    f"({row['horario_inicio']} às {row['horario_fim']})"
                                )
                                st.write(
                                    f"**Prof:** {row['professor']} | "
                                    f"**Disciplina:** {row['disciplina']}"
                                )
                                with st.expander("👁️ Ver materiais solicitados"):
                                    mats = core.obter_detalhes_materiais(row["id"])
                                    if mats:
                                        st.dataframe(
                                            pd.DataFrame(mats)[
                                                ["Item", "Qtd Pedida", "Unidade"]
                                            ],
                                            hide_index=True,
                                        )
                                    else:
                                        st.write("Nenhum material listado.")
                            with c2:
                                if st.button(
                                    "✅ Aprovar",
                                    key=f"apr_{row['id']}",
                                    use_container_width=True,
                                ):
                                    core.atualizar_status(row["id"], "RESERVADO")
                                    st.rerun()
                                if st.button(
                                    "❌ Recusar",
                                    key=f"rec_{row['id']}",
                                    use_container_width=True,
                                ):
                                    core.atualizar_status(row["id"], "RECUSADO")
                                    st.rerun()

            with tab_historico:
                st.subheader("📝 Histórico de Aulas Finalizadas")
                conn = core.conectar()
                query_h = """
                    SELECT a.data, l.nome AS lab, a.professor, a.disciplina, a.curso
                    FROM agendamentos a
                    JOIN laboratorios l ON a.id_lab = l.id
                    WHERE a.status = 'FINALIZADO'
                    ORDER BY a.id DESC
                """
                df_h = pd.read_sql_query(query_h, conn)
                conn.close()
                st.dataframe(df_h, use_container_width=True, hide_index=True)

            with tab_calendario:
                st.subheader("📅 Cronograma Geral")
                conn = core.conectar()
                df_labs = pd.read_sql_query("SELECT nome FROM laboratorios", conn)
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    data_f = st.date_input("A partir de:", datetime.date.today())
                with col_f2:
                    labs_f = st.multiselect(
                        "Filtrar Laboratórios:", df_labs["nome"].tolist()
                    )

                query_cal = """
                    SELECT a.data, a.horario_inicio, a.horario_fim, l.nome AS lab,
                        a.professor, a.status
                    FROM agendamentos a
                    JOIN laboratorios l ON a.id_lab = l.id
                    WHERE a.status != 'RECUSADO'
                    ORDER BY a.data ASC
                """
                df_cal = pd.read_sql_query(query_cal, conn)
                conn.close()

                if not df_cal.empty:
                    df_cal["dt"] = pd.to_datetime(df_cal["data"]).dt.date
                    df_cal = df_cal[df_cal["dt"] >= data_f]
                    if labs_f:
                        df_cal = df_cal[df_cal["lab"].isin(labs_f)]
                    st.dataframe(
                        df_cal.drop(columns=["dt"]),
                        use_container_width=True,
                        hide_index=True,
                    )

        elif st.session_state.submenu_coord == "Infraestrutura":
            tab_inventario, tab_equipe, tab_indicadores = st.tabs(
                ["📦 Gestão de Inventário e Laboratórios", "👥 Equipe Técnica", "📈 Indicadores"]
            )

            with tab_inventario:
                st.subheader("🏢 Controle de Unidades e Materiais")
                conn = core.conectar()

                with st.expander("➕ Cadastrar Novo Laboratório"):
                    with st.form("form_novo_lab"):
                        col_n1, col_n2 = st.columns(2)
                        nome_novo = col_n1.text_input("Nome do Laboratório")
                        bloco_novo = col_n1.selectbox(
                            "Bloco",
                            [
                                "Bloco A",
                                "Bloco B",
                                "Bloco C",
                                "Bloco D",
                                "Bloco M",
                            ],
                        )
                        cap_novo = col_n2.number_input(
                            "Capacidade de Alunos", min_value=1, step=1
                        )
                        status_novo = col_n2.selectbox(
                            "Status Inicial", ["Ativo", "Manutenção", "Desativado"]
                        )

                        if st.form_submit_button("Salvar Laboratório"):
                            if nome_novo:
                                try:
                                    c = conn.cursor()
                                    c.execute(
                                        """
                                        INSERT INTO laboratorios
                                            (nome, bloco, capacidade, status_lab)
                                        VALUES (?, ?, ?, ?)
                                        """,
                                        (nome_novo, bloco_novo, cap_novo, status_novo),
                                    )
                                    conn.commit()
                                    st.success(
                                        f"Laboratório '{nome_novo}' cadastrado!"
                                    )
                                    st.rerun()
                                except Exception as e:
                                    logger.exception("Erro ao cadastrar novo laboratório")
                                    st.error(f"Erro ao cadastrar: {e}")
                            else:
                                st.warning("O nome do laboratório é obrigatório.")

                df_labs = pd.read_sql_query("SELECT id, nome FROM laboratorios", conn)
                dict_labs = {row["nome"]: row["id"] for _, row in df_labs.iterrows()}
                lab_sel = st.selectbox(
                    "Escolha o laboratório para gerenciar:",
                    ["-- Selecione --"] + list(dict_labs.keys()),
                )

                if lab_sel != "-- Selecione --":
                    id_lab_gestao = dict_labs[lab_sel]
                    sub_dados, sub_estoque, sub_import = st.tabs(
                        ["📋 Dados do Laboratório", "📦 Estoque", "📤 Importar Excel"]
                    )

                    with sub_dados:
                        df_infra = pd.read_sql_query(
                            "SELECT * FROM laboratorios WHERE id = ?",
                            conn,
                            params=(id_lab_gestao,),
                        )

                        # Normaliza capacidade para int (evita bytes/str estranhas)
                        if not df_infra.empty:
                            cap_val = df_infra.loc[0, "capacidade"]
                            try:
                                df_infra.loc[0, "capacidade"] = int(cap_val)
                            except (TypeError, ValueError):
                                df_infra.loc[0, "capacidade"] = 0

                        edit_infra = st.data_editor(
                            df_infra,
                            hide_index=True,
                            key=f"infra_{id_lab_gestao}",
                        )
                        if st.button("Salvar Alterações do Lab"):
                            c = conn.cursor()
                            cap_edit_val = edit_infra.iloc[0]["capacidade"]
                            try:
                                cap_edit_int = int(cap_edit_val)
                            except (TypeError, ValueError):
                                cap_edit_int = 0

                            c.execute(
                                """
                                UPDATE laboratorios
                                SET nome=?, bloco=?, capacidade=?, status_lab=?
                                WHERE id=?
                                """,
                                (
                                    edit_infra.iloc[0]["nome"],
                                    edit_infra.iloc[0]["bloco"],
                                    cap_edit_int,
                                    edit_infra.iloc[0]["status_lab"],
                                    id_lab_gestao,
                                ),
                            )
                            conn.commit()
                            st.success("Dados atualizados!")
                            st.rerun()

                    with sub_estoque:
                        # Carrega o estoque apenas do laboratório selecionado
                        df_inv = pd.read_sql_query(
                            "SELECT * FROM insumos WHERE id_lab = ?",
                            conn,
                            params=(id_lab_gestao,),
                        )

                        # Garante que as colunas existam, mesmo em base vazia
                        if df_inv.empty:
                            df_inv = pd.DataFrame(
                                columns=[
                                    "id",
                                    "nome",
                                    "categoria",
                                    "quantidade",
                                    "unidade",
                                    "estoque_minimo",
                                    "id_lab",
                                ]
                            )

                        # Oculta a coluna id_lab na edição (vai ser preenchida automaticamente)
                        colunas_visiveis = [
                            col for col in df_inv.columns if col not in ("id", "id_lab")
                        ]

                        # Categoria: lista suspensa baseada nos cabeçalhos
                        category_options = ["Consumível", "Não Consumível", "Equipamento"]

                        # Configuração da data_editor para listas suspensas de categoria
                        column_config = {
                            "categoria": st.column_config.SelectboxColumn(
                                "Categoria",
                                options=category_options,
                            ),
                        }

                        edit_inv = st.data_editor(
                            df_inv[colunas_visiveis],
                            num_rows="dynamic",
                            hide_index=True,
                            key=f"inv_{id_lab_gestao}",
                            column_config=column_config,
                        )

                        if st.button("Salvar Estoque"):
                            c = conn.cursor()

                            # Remove tudo daquele laboratório para regravar a tabela
                            c.execute(
                                "DELETE FROM insumos WHERE id_lab = ?",
                                (id_lab_gestao,),
                            )

                            # Reconstrói o DataFrame com as colunas completas
                            df_to_save = edit_inv.copy()

                            # Remove linhas totalmente vazias (sem nome)
                            if "nome" in df_to_save.columns:
                                df_to_save = df_to_save[
                                    df_to_save["nome"].astype(str).str.strip() != ""
                                ]

                            # Se o usuário não preencheu nada, não grava nada
                            if not df_to_save.empty:
                                # Garante todas as colunas esperadas
                                for col in [
                                    "nome",
                                    "categoria",
                                    "quantidade",
                                    "unidade",
                                    "estoque_minimo",
                                ]:
                                    if col not in df_to_save.columns:
                                        df_to_save[col] = None

                                # Preenche automaticamente o id_lab com o laboratório selecionado
                                df_to_save["id_lab"] = id_lab_gestao

                                # Normaliza tipos numéricos
                                for numeric_col in ["quantidade", "estoque_minimo"]:
                                    if numeric_col in df_to_save.columns:
                                        df_to_save[numeric_col] = pd.to_numeric(
                                            df_to_save[numeric_col],
                                            errors="coerce",
                                        )

                                # Grava sem a coluna id (autoincremento será gerado pelo banco)
                                df_to_save.to_sql(
                                    "insumos",
                                    conn,
                                    if_exists="append",
                                    index=False,
                                )

                            st.success("Estoque atualizado!")
                            st.rerun()

            with tab_equipe:
                st.subheader("👥 Gestão da Equipe Técnica")
                conn = core.conectar()

                with st.expander("➕ Adicionar Novo Integrante"):
                    with st.form("form_equipe"):
                        nome_tec = st.text_input("Nome do Técnico")
                        cargo_tec = st.selectbox(
                            "Cargo/Função",
                            [
                                "Técnico de Laboratório",
                                "Líder Técnico",
                                "Auxiliar",
                            ],
                        )

                        df_labs_tec = pd.read_sql_query(
                            "SELECT id, nome FROM laboratorios", conn
                        )

                        if df_labs_tec.empty:
                            st.warning(
                                "Nenhum laboratório cadastrado. Cadastre um laboratório antes de vincular a equipe."
                            )
                            lab_vinc = None
                            id_lab_vinc = None
                        else:
                            lab_vinc = st.selectbox(
                                "Laboratório de Referência",
                                df_labs_tec["nome"].tolist(),
                            )

                            # Garante que o filtro encontrou uma linha antes de acessar [0]
                            match = df_labs_tec[df_labs_tec["nome"] == lab_vinc]
                            id_lab_vinc = int(match["id"].iloc[0]) if not match.empty else None

                        if st.form_submit_button("Cadastrar Técnico"):
                            if not nome_tec:
                                st.warning("Informe o nome do técnico.")
                            elif id_lab_vinc is None:
                                st.warning("Selecione um laboratório válido para vincular o técnico.")
                            else:
                                c = conn.cursor()
                                c.execute(
                                    """
                                    INSERT INTO equipe (nome, cargo, id_lab_responsavel)
                                    VALUES (?, ?, ?)
                                    """,
                                    (nome_tec, cargo_tec, id_lab_vinc),
                                )
                                conn.commit()
                                st.success("Técnico adicionado à equipe!")
                                st.rerun()

                st.write("### Integrantes Cadastrados")
                query_equipe = """
                    SELECT e.nome, e.cargo, l.nome as laboratorio
                    FROM equipe e
                    LEFT JOIN laboratorios l
                    ON e.id_lab_responsavel = l.id
                """
                df_equipe = pd.read_sql_query(query_equipe, conn)
                st.dataframe(df_equipe, use_container_width=True, hide_index=True)
                conn.close()

            with tab_indicadores:
                st.subheader("📈 Dashboards de Performance")
                conn = core.conectar()
                df_e = pd.read_sql_query("SELECT * FROM insumos", conn)
                df_a = pd.read_sql_query(
                    """
                    SELECT a.*, l.nome as lab_nome
                    FROM agendamentos a
                    JOIN laboratorios l ON a.id_lab = l.id
                    WHERE a.status = 'FINALIZADO'
                    """,
                    conn,
                )
                df_labs = pd.read_sql_query("SELECT * FROM laboratorios", conn)
                conn.close()

                k1, k2, k3 = st.columns(3)
                k1.metric("Total de Itens", len(df_e))
                k2.metric("Aulas Realizadas", len(df_a))
                k3.metric("Labs Ativos", len(df_labs[df_labs["status_lab"] == "Ativo"]))

                if not df_a.empty:
                    st.write("**Ocupação por Laboratório**")
                    st.bar_chart(df_a["lab_nome"].value_counts())

    # ========================================================
    # PÁGINA TÉCNICO
    # ========================================================
    elif st.session_state.perfil == "Técnico":
        st.header("🛠️ Painel de Operação Técnica")

        conn = core.conectar()
        df_labs = pd.read_sql_query("SELECT id, nome FROM laboratorios", conn)
        dict_labs = {row["nome"]: row["id"] for _, row in df_labs.iterrows()}

        lab_selecionado = st.selectbox(
            "Selecione o Laboratório para gerenciar:",
            ["-- Selecione --"] + list(dict_labs.keys()),
        )

        if lab_selecionado != "-- Selecione --":
            id_lab_atual = dict_labs[lab_selecionado]

            tab_aulas, tab_estoque = st.tabs(["📋 Aulas do Dia", "📦 Estoque Local"])

            # -----------------------------
            # Aba: Aulas do Dia (detalhadas)
            # -----------------------------
            with tab_aulas:
                query_aulas = """
                    SELECT *
                    FROM agendamentos
                    WHERE id_lab = ?
                    AND status IN ('RESERVADO', 'OCUPADO')
                    ORDER BY data ASC, horario_inicio ASC
                """
                df_t = pd.read_sql_query(query_aulas, conn, params=(id_lab_atual,))

                # Garante que a coluna id exista e seja inteiro
                if "id" in df_t.columns:
                    try:
                        df_t["id"] = df_t["id"].astype(int)
                    except Exception as e:
                        logger.exception("Falha ao converter coluna id para int em df_t")
                        df_t = df_t.iloc[0:0]

                if df_t.empty:
                    st.info(f"Não há aulas pendentes para o {lab_selecionado}.")
                else:
                    st.subheader(f"Aulas para {lab_selecionado}")

                    for _, aula in df_t.iterrows():
                        agendamento_id = int(aula["id"])

                        with st.container(border=True):
                            # Linha principal com informações gerais
                            c1, c2 = st.columns([3, 1])

                            with c1:
                                st.markdown(
                                    f"**📚 Disciplina:** {aula['disciplina']}  \n"
                                    f"**👨‍🏫 Professor:** {aula['professor']}  \n"
                                    f"**🎓 Curso:** {aula['curso']}  \n"
                                    f"**👥 Alunos:** {aula['qtd_alunos']}"
                                )
                                st.markdown(
                                    f"**📅 Data:** {aula['data']}  \n"
                                    f"**⏰ Horário:** {aula['horario_inicio']} - {aula['horario_fim']}  \n"
                                    f"**🟢 Status:** {aula['status']}"
                                )

                            with c2:
                                # Botão para marcar como OCUPADO (início da aula)
                                if aula["status"] == "RESERVADO":
                                    if st.button(
                                        "Iniciar Aula",
                                        key=f"iniciar_{agendamento_id}",
                                        use_container_width=True,
                                    ):
                                        core.atualizar_status(agendamento_id, "OCUPADO")
                                        st.rerun()
                                # Botão para finalizar
                                if aula["status"] == "OCUPADO":
                                    if st.button(
                                        "Finalizar Aula",
                                        key=f"finalizar_{agendamento_id}",
                                        use_container_width=True,
                                    ):
                                        core.atualizar_status(agendamento_id, "FINALIZADO")
                                        st.rerun()

                            # Detalhes de materiais e roteiro
                            st.markdown("---")
                            col_mats, col_roteiro = st.columns(2)

                            with col_mats:
                                st.markdown("**📦 Materiais Solicitados**")
                                mats = core.obter_detalhes_materiais(agendamento_id)

                                if not mats:
                                    st.write("Nenhum material registrado para esta aula.")
                                else:
                                    df_mats = pd.DataFrame(mats)

                                    # 1) Exibição básica (igual à do Coordenador)
                                    colunas_basicas = [
                                        col
                                        for col in ["Item", "Qtd Pedida", "Unidade"]
                                        if col in df_mats.columns
                                    ]
                                    if colunas_basicas:
                                        st.dataframe(
                                            df_mats[colunas_basicas],
                                            hide_index=True,
                                            use_container_width=True,
                                        )

                                    # Normaliza coluna Categoria (se existir)
                                    if "Categoria" in df_mats.columns:
                                        df_mats["Categoria"] = (
                                            df_mats["Categoria"]
                                            .astype(str)
                                            .str.strip()
                                            .replace("", "Desconhecido")
                                        )
                                    else:
                                        df_mats["Categoria"] = "Desconhecido"

                                    # Coluna auxiliar para comparações case-insensitive,
                                    # removendo acentos básicos
                                    df_mats["Categoria_normalizada"] = (
                                        df_mats["Categoria"]
                                        .str.lower()
                                        .str.strip()
                                        .str.normalize("NFKD")
                                        .str.encode("ascii", errors="ignore")
                                        .str.decode("ascii")
                                    )

                                    # 2) Exibição separada por categoria (informativo)
                                    st.markdown("**Por categoria:**")
                                    for categoria in [
                                        "Consumível",
                                        "Não Consumível",
                                        "Equipamento",
                                        "Desconhecido",
                                    ]:
                                        df_cat = df_mats[
                                            df_mats["Categoria"] == categoria
                                        ]
                                        if not df_cat.empty:
                                            st.markdown(f"**{categoria}**")
                                            st.dataframe(
                                                df_cat[
                                                    ["Item", "Qtd Pedida", "Unidade"]
                                                ],
                                                hide_index=True,
                                                use_container_width=True,
                                            )

                                    # 3) Ajuste pós-aula para CONSUMÍVEIS
                                    #    REGRA: só aparece quando a aula estiver RESERVADA ou EM ANDAMENTO
                                    if aula["status"] in ("RESERVADO", "OCUPADO"):
                                        # Considera consumível qualquer categoria cuja forma normalizada
                                        # contenha "consum" (pega "consumivel", "consumíveis", etc.)
                                        df_consumiveis = df_mats[
                                            df_mats["Categoria_normalizada"].str.contains(
                                                "consum", na=False
                                            )
                                        ]

                                        if not df_consumiveis.empty:
                                            st.markdown(
                                                "### 🔄 Ajuste de Consumo Real (Consumíveis)"
                                            )
                                            st.caption(
                                                "Informe abaixo quanto foi realmente utilizado em cada item consumível. "
                                                "Ao aplicar o ajuste, o estoque do laboratório será atualizado."
                                            )

                                            df_edit = df_consumiveis.copy()
                                            df_edit["Qtd Utilizada"] = df_edit[
                                                "Qtd Pedida"
                                            ]

                                            df_edit = st.data_editor(
                                                df_edit[
                                                    [
                                                        "Item",
                                                        "Qtd Pedida",
                                                        "Unidade",
                                                        "Qtd Utilizada",
                                                    ]
                                                ],
                                                num_rows="fixed",
                                                hide_index=True,
                                                key=f"ajuste_consumo_{agendamento_id}",
                                            )

                                            if st.button(
                                                "Aplicar baixa no estoque (consumo real)",
                                                key=f"btn_baixa_{agendamento_id}",
                                                help=(
                                                    "Atualiza o estoque deste laboratório, "
                                                    "descontando apenas o que foi realmente utilizado "
                                                    "para os itens consumíveis."
                                                ),
                                            ):
                                                materiais_usados = {}
                                                for _, linha in df_edit.iterrows():
                                                    item_exib = (
                                                        f"{linha['Item']} ({linha['Unidade']})"
                                                    )
                                                    try:
                                                        qtd_usada = float(
                                                            linha["Qtd Utilizada"]
                                                        )
                                                    except Exception as e:
                                                        logger.exception("Falha ao converter Qtd Utilizada para float")
                                                        qtd_usada = 0.0

                                                    if qtd_usada > 0:
                                                        materiais_usados[
                                                            item_exib
                                                        ] = qtd_usada

                                                if materiais_usados:
                                                    ok = core.processar_baixa_estoque_real(
                                                        agendamento_id,
                                                        materiais_usados,
                                                    )
                                                    if ok:
                                                        st.success(
                                                            "Baixa de estoque realizada com sucesso!"
                                                        )
                                                else:
                                                    st.info(
                                                        "Nenhuma quantidade positiva informada para baixa."
                                                    )

                            with col_roteiro:
                                st.markdown("**📝 Roteiro / Observações**")
                                roteiro = aula["roteiro"]
                                if roteiro and str(roteiro).strip():
                                    st.write(roteiro)
                                else:
                                    st.write("Nenhuma descrição de roteiro foi informada.")

