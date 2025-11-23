"""Aplicação Streamlit para explorar estatísticas de Pokémons.

Este app consome apenas os arquivos CSV gerados pelo ETL na pasta
`data/processed` e permite:

- Filtrar pokémons por tipo, atributos e se são lendários ou não.
- Visualizar KPIs gerais de quantidade de pokémons e combates.
- Ver rankings de top vencedores e perdedores.
- Analisar taxa de vitória por pokémon e por tipo.
- Ver correlação entre atributos (ataque, defesa, HP, velocidade) e
	taxa de vitória.
- Sugerir uma equipe de 6 pokémons com boa performance e diversidade.
- Baixar os dados filtrados em CSV para outras análises.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st
import altair as alt

DATA_PROC = Path("data/processed")
PALETTE = {
	"primary": "#81A856",  # Verde para destaques e textos numéricos
	"secondary": "#F1F1F1",  # Branco para títulos/textos sobre fundo escuro
	"dark": "#027373",  # Azul-esverdeado escuro (sidebar)
	"accent": "#D9D05B",  # Amarelo/mostarda para sliders e detalhes
	"background": "#03A6A6",  # Ciano para fundo principal
}


@st.cache_data
def load_csv(path: Path) -> pd.DataFrame:
	"""Carrega um CSV em um DataFrame, com cache em memória.

	Se o arquivo não existir, devolve um DataFrame vazio para evitar
	erros na interface.
	"""
	if not path.exists():
		return pd.DataFrame()
	return pd.read_csv(path)


def main() -> None:
	"""Função principal do app Streamlit.

	Carrega os CSVs processados, constrói os filtros na barra lateral e
	organiza todas as seções de KPIs, tabelas, gráficos e downloads.
	"""
	st.set_page_config(page_title="Pokémon Dashboard", layout="wide")
	st.markdown(
		f"""
		<style>
		.stApp {{
			background-color: {PALETTE["background"]};
			color: {PALETTE["secondary"]};
		}}
		header[data-testid="stHeader"] {{
			background: {PALETTE["background"]};
		}}
		h1, h2, h3 {{
			color: {PALETTE["secondary"]};
		}}
		div[data-testid="stMetricValue"] {{
			color: {PALETTE["secondary"]};
		}}
		div[data-testid="stMetricLabel"] {{
			color: {PALETTE["secondary"]};
		}}
		.stDataFrame {{
			background-color: {PALETTE["dark"]};
			border-radius: 8px;
			padding: 0.5rem;
		}}
		.stDataFrame thead tr th {{
			background-color: {PALETTE["dark"]};
			color: {PALETTE["secondary"]};
		}}
		.stDataFrame tbody tr {{
			color: {PALETTE["secondary"]};
		}}
		.stDataFrame tbody tr:nth-child(even) {{
			background-color: {PALETTE["dark"]}EE;
		}}
		div[data-testid="stSidebar"] {{
			background-color: {PALETTE["dark"]};
		}}
		div[data-testid="stSidebar"] * {{
			color: {PALETTE["secondary"]} !important;
		}}
		div[data-testid="stSidebar"] [data-baseweb="slider"] > div:first-child {{
			background-color: {PALETTE["accent"]}55;
		}}
		div[data-testid="stSidebar"] [data-baseweb="slider"] > div:first-child > div {{
			background-color: {PALETTE["accent"]};
		}}
		div[data-testid="stSidebar"] [data-baseweb="slider"] div[role="slider"] {{
			background-color: {PALETTE["secondary"]};
			border: 2px solid {PALETTE["accent"]};
		}}
		</style>
		""",
		unsafe_allow_html=True,
	)
	st.title("Pokémon Dashboard")

	# Carrega todos os arquivos processados gerados pelo ETL
	pokemon = load_csv(DATA_PROC / "pokemon.csv")
	combats = load_csv(DATA_PROC / "combats.csv")
	stats = load_csv(DATA_PROC / "pokemon_stats.csv")
	by_type = load_csv(DATA_PROC / "pokemon_by_type.csv")

	# Filtros na barra lateral
	st.sidebar.header("Filtros")
	# Lista de tipos únicos presentes na coluna "types" do DataFrame
	types = sorted(list({t for ts in pokemon.get("types", pd.Series()).fillna("") for t in str(ts).split("/") if t})) if not pokemon.empty else []
	sel_types = st.sidebar.multiselect("Tipo do Pokémon", types)
	include_legendaries = st.sidebar.checkbox("Incluir lendários", value=True)
	min_battles = 0 if stats.empty or "total_combats" not in stats.columns else st.sidebar.slider(
		"Mínimo de combates", 0, int(stats["total_combats"].max()), 0
	)

	def _filter_by_types(df: pd.DataFrame) -> pd.DataFrame:
		"""Filtra um DataFrame pelo(s) tipo(s) selecionado(s) na sidebar."""
		if not sel_types or df.empty:
			return df
		return df[df["types"].fillna("").apply(lambda s: any(t in str(s).split("/") for t in sel_types))]

	# Filtros por faixa de atributos numéricos (ataque, defesa, HP, velocidade)
	for col in ["attack", "defense", "hp", "speed"]:
		if col in pokemon.columns:
			min_v, max_v = int(pokemon[col].min()), int(pokemon[col].max())
			lo, hi = st.sidebar.slider(col.capitalize(), min_v, max_v, (min_v, max_v))
			pokemon = pokemon[(pokemon[col] >= lo) & (pokemon[col] <= hi)]
			# Em stats, mantemos apenas pokémons dentro da faixa ou valores ausentes
			stats = stats[(stats[col].isna()) | ((stats[col] >= lo) & (stats[col] <= hi))]

	# Aplica o filtro de tipos ao DataFrame de pokémons
	pokemon = _filter_by_types(pokemon)
	# Traz colunas úteis (legendary, types) para stats e aplica filtros adicionais
	if not pokemon.empty and "id" in stats.columns:
		cols_to_join = [c for c in ["id", "name", "legendary", "types"] if c in pokemon.columns]
		stats = stats.merge(pokemon[cols_to_join], on=[c for c in ["id", "name"] if c in cols_to_join], how="inner")
	if not include_legendaries and "legendary" in stats.columns:
		# Se o checkbox estiver desmarcado, remove pokémons marcados como lendários
		stats = stats[stats["legendary"].astype(str).str.lower().isin(["false", "0", "no"])].copy()
	if "total_combats" in stats.columns:
		stats = stats[stats["total_combats"] >= min_battles]

	# KPIs principais do topo do dashboard
	c1, c2, c3 = st.columns(3)
	with c1:
		st.metric("Total de Pokémons", 0 if pokemon.empty else len(pokemon))
	with c2:
		pok_in_comb = 0 if combats.empty else len(pd.unique(pd.concat([combats["first_pokemon"], combats["second_pokemon"]], ignore_index=True)))
		st.metric("Pokémons em combate", pok_in_comb)
	with c3:
		st.metric("Total de combates", 0 if combats.empty else len(combats))

	st.subheader("Tabela de Pokémons")
	st.dataframe(pokemon if not pokemon.empty else pd.DataFrame(), width="stretch")

	# Seções de ranking: top vencedores e top perdedores
	colA, colB = st.columns(2)
	with colA:
		st.subheader("Top 10 Vencedores")
		if not stats.empty and "wins" in stats.columns:
			st.dataframe(stats.sort_values(["wins", "win_rate"], ascending=[False, False]).head(10)[["name", "wins", "win_rate"]])
		else:
			st.info("Sem dados de vitórias para exibir.")
	with colB:
		st.subheader("Top 10 Perdedores")
		if not stats.empty and "losses" in stats.columns:
			st.dataframe(stats.sort_values(["losses", "win_rate"], ascending=[False, True]).head(10)[["name", "losses", "win_rate"]])
		else:
			st.info("Sem dados de derrotas para exibir.")

	st.subheader("Taxa de vitória por Pokémon")
	if not stats.empty:
		st.dataframe(stats[["name", "wins", "losses", "total_combats", "win_rate"]].sort_values("win_rate", ascending=False))

	# Win rate média por tipo (agrupando por tipos primário/secundário)
	st.subheader("Taxa de vitória média por tipo")
	if not stats.empty and "types" in stats.columns:
		tmp = stats.copy()
		tmp = tmp.assign(type=tmp["types"].astype(str).str.split("/")).explode("type")
		by_type_rate = tmp.groupby("type")["win_rate"].mean().sort_values(ascending=False).reset_index()
		chart = alt.Chart(by_type_rate).mark_bar(color=PALETTE["accent"]).encode(
			x=alt.X("type", sort="-y"),
			y=alt.Y("win_rate", title="Win Rate médio"),
			tooltip=["type", alt.Tooltip("win_rate", format=".2%")]
		).configure_view(strokeWidth=0)
		st.altair_chart(chart, width="stretch")

	# Correlação atributos x win_rate
	st.subheader("Correlação de atributos com taxa de vitória")
	if not stats.empty:
		num_cols = [c for c in ["attack", "defense", "hp", "speed"] if c in stats.columns]
		if num_cols and "win_rate" in stats.columns:
			corr = stats[num_cols + ["win_rate"]].corr(numeric_only=True)["win_rate"].drop("win_rate")
			corr_df = corr.reset_index().rename(columns={"index": "atributo", "win_rate": "correlacao"}).sort_values("correlacao", ascending=False)
			chart = alt.Chart(corr_df).mark_bar(color=PALETTE["primary"]).encode(
				x=alt.X("atributo", sort="-y"),
				y=alt.Y("correlacao", scale=alt.Scale(domain=[-1, 1])),
				tooltip=["atributo", alt.Tooltip("correlacao", format=".2f")]
			).configure_view(strokeWidth=0)
			st.altair_chart(chart, width="stretch")
			st.dataframe(corr_df)

	# Sugestão de equipe com 6 pokémons
	st.subheader("Sugestão de equipe (6)")

	def suggest_team(df: pd.DataFrame, size: int = 6) -> pd.DataFrame:
		"""Sugere uma equipe dando preferência a alta win_rate e diversidade.

		Ordena os pokémons por taxa de vitória e número de vitórias e, em
		seguida, seleciona até `size` pokémons tentando não repetir muito o
		tipo primário, priorizando diversidade.
		"""
		if df.empty:
			return df
		df = df.sort_values(["win_rate", "wins"], ascending=[False, False]).copy()
		team = []
		used_types = set()
		for _, row in df.iterrows():
			types = str(row.get("types", "")).split("/")
			t1 = types[0] if types else ""
			# Foca em diversidade; permite completar slots finais se necessário
			if t1 not in used_types or len(team) >= size - 2:
				team.append(row)
				used_types.add(t1)
			if len(team) == size:
				break
		return pd.DataFrame(team)

	if not stats.empty:
		team = suggest_team(stats)
		st.dataframe(team[[c for c in ["name", "types", "wins", "losses", "total_combats", "win_rate", "attack", "defense", "hp", "speed"] if c in team.columns]])

	# Área de downloads dos dados filtrados
	st.subheader("Downloads")
	if not pokemon.empty:
		st.download_button("Baixar Pokémon (CSV)", pokemon.to_csv(index=False).encode("utf-8"), file_name="pokemon.csv", mime="text/csv")
	if not stats.empty:
		st.download_button("Baixar Estatísticas (CSV)", stats.to_csv(index=False).encode("utf-8"), file_name="pokemon_stats.csv", mime="text/csv")

	st.subheader("Distribuição por tipo (Pokémons)")
	if not by_type.empty:
		bt = by_type.copy()
		if sel_types:
			bt = bt[bt["type"].isin(sel_types)]
		bar_chart = alt.Chart(bt).mark_bar(color=PALETTE["dark"]).encode(
			x=alt.X("type", sort="-y"),
			y=alt.Y("count", title="Quantidade"),
			tooltip=["type", "count"],
		).configure_view(strokeWidth=0)
		st.altair_chart(bar_chart, width="stretch")

	st.caption("Fonte: API Pokémon")


if __name__ == "__main__":
	main()
