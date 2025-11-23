"""Pipeline ETL para dados da API Pokémon.

Este módulo é responsável por:

- Extrair dados brutos da API (pokémons básicos, atributos e combates).
- Fazer cache incremental em arquivos JSON na pasta `data/raw` para
	evitar baixar tudo novamente em cada execução.
- Transformar os dados em tabelas analíticas (CSV) na pasta
	`data/processed`, prontas para consumo pelo Streamlit ou outras
	ferramentas (como Excel ou Power BI).

O fluxo principal é:
- `extract_all()` → baixa e/ou reutiliza JSONs em `data/raw`.
- `transform()` → lê os JSONs, gera CSVs e calcula estatísticas.
- `run()` → ponto de entrada que executa o ETL completo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

import pandas as pd

from .api_client import ApiClient, ApiConfig


DATA_RAW = Path("data/raw")
DATA_PROC = Path("data/processed")


def ensure_dirs() -> None:
	"""Garante que as pastas `data/raw` e `data/processed` existam."""
	DATA_RAW.mkdir(parents=True, exist_ok=True)
	DATA_PROC.mkdir(parents=True, exist_ok=True)


def _should_refresh() -> bool:
	"""Indica se deve forçar o recarregamento dos dados da API.

	Controlado pela variável de ambiente `FORCE_REFRESH`.
	Se definida como `1`, `true` ou `True`, ignora o cache local e
	refaz o download dos dados.
	"""
	return os.getenv("FORCE_REFRESH", "0").strip() in {"1", "true", "True"}


def _read_json(path: Path):
	"""Lê um arquivo JSON de `path` e devolve o conteúdo carregado."""
	with path.open("r", encoding="utf-8") as f:
		return json.load(f)


def extract_all() -> Dict[str, Path]:
	"""Extrai todos os dados necessários da API, com uso de cache.

	Etapas:
	1. Pokémons básicos → `pokemon_basic.json`.
	2. Atributos completos de cada pokémon → `pokemon_attributes.json`.
	3. Combates → `combats.json`.

	Retorna um dicionário com os caminhos dos arquivos JSON gerados existentes.
	"""
	cfg = ApiConfig.from_env()
	client = ApiClient(cfg)
	ensure_dirs()

	# 1) Pokémons básicos (com cache)
	path_basic = DATA_RAW / "pokemon_basic.json"
	if path_basic.exists() and not _should_refresh():
		# Se já existe e não forçado refresh, apenas reutiliza o arquivo
		pokemon_basic: List[Dict] = _read_json(path_basic)
	else:
		# Caso contrário, baixa todos os registros da API
		pokemon_basic = list(client.iter_all_pokemon())
		path_basic.write_text(json.dumps(pokemon_basic, ensure_ascii=False, indent=2), encoding="utf-8")

	# 2) Atributos (cache + incremental)
	path_attrs = DATA_RAW / "pokemon_attributes.json"
	attributes: List[Dict] = []
	if path_attrs.exists() and not _should_refresh():
		# Lê atributos atuais e identifica quais IDs ainda não foram baixados
		attributes = _read_json(path_attrs)
		existing_ids = {int(a.get("id")) for a in attributes if "id" in a}
		missing = [int(p["id"]) for p in pokemon_basic if int(p["id"]) not in existing_ids]
	else:
		# Se não há arquivo ou FORCER_REFRESH=1, assume que todos estão faltando
		missing = [int(p["id"]) for p in pokemon_basic]

	import time
	for pid in missing:
		# Busca atributos de cada pokémon faltante
		attributes.append(client.get_pokemon_attributes(pid))
		# Pequena pausa para evitar bater no rate limit da API
		time.sleep(0.02)
	# Faz merge com atributos antigos (se houver) e remove duplicados por ID
	if path_attrs.exists() and not _should_refresh():
		old = {int(a.get("id")): a for a in _read_json(path_attrs) if "id" in a}
		for a in attributes:
			old[int(a.get("id"))] = a
		attributes = list(old.values())
	path_attrs.write_text(json.dumps(attributes, ensure_ascii=False, indent=2), encoding="utf-8")

	# 3) Combates (cache, limitado por MAX_COMBATS na ApiConfig)
	path_comb = DATA_RAW / "combats.json"
	if path_comb.exists() and not _should_refresh():
		# Já existe e não foi forçado refresh: mantém o arquivo atual
		pass
	else:
		combats: List[Dict] = []
		for c in client.iter_all_combats():
			combats.append(c)
			# Salva periodicamente para não perder progresso em execuções longas
			if len(combats) % 500 == 0:
				path_comb.write_text(json.dumps(combats, ensure_ascii=False, indent=2), encoding="utf-8")
		path_comb.write_text(json.dumps(combats, ensure_ascii=False, indent=2), encoding="utf-8")

	return {
		"pokemon_basic": path_basic,
		"pokemon_attributes": path_attrs,
		"combats": path_comb,
	}


def transform(raw_paths: Dict[str, Path]) -> Dict[str, Path]:
	"""Transforma os JSONs brutos em CSVs analíticos.

	- Normaliza colunas de atributos (tipos, nomes em minúsculo etc.).
	- Constrói tabela de combates com nomes legíveis de pokémons.
	- Calcula vitórias, derrotas, total de combates e taxa de vitória.
	- Gera tabelas auxiliares (top vencedores, top perdedores, por tipo).
	"""
	ensure_dirs()
	attrs = pd.read_json(raw_paths["pokemon_attributes"]) if raw_paths.get("pokemon_attributes") else pd.DataFrame()
	combats = pd.read_json(raw_paths["combats"]) if raw_paths.get("combats") and raw_paths["combats"].exists() else pd.DataFrame()

	# Normalização das colunas de atributos
	if not attrs.empty:
		# Garante nomes de colunas em minúsculo para facilitar merges
		attrs.columns = [c.lower() for c in attrs.columns]
		# Separa a string de tipos em duas colunas (tipo primário e secundário)
		attrs["type_1"] = attrs["types"].astype(str).str.split("/").str[0]
		attrs["type_2"] = attrs["types"].astype(str).str.split("/").str[1].fillna("")
		attrs.to_csv(DATA_PROC / "pokemon.csv", index=False)

	# Preparação dos dados de combates
	if not combats.empty:
		combats.columns = [c.lower() for c in combats.columns]
		# Mantém somente as colunas relevantes: primeiro, segundo e vencedor
		combats = combats[["first_pokemon", "second_pokemon", "winner"]]

		name_by_id = None
		if not attrs.empty:
			# Mapa de ID numérico -> nome do pokémon para deixar as tabelas legíveis
			name_by_id = dict(zip(attrs["id"].astype(int), attrs["name"].astype(str)))

		def normalize_name(x: str) -> str:
			"""Converte IDs numéricos em nomes de pokémons, se possível."""
			s = str(x)
			if s.isdigit() and name_by_id:
				return str(name_by_id.get(int(s), s))
			return s

		# Normaliza as três colunas de pokémons (primeiro, segundo e vencedor)
		for col in ["first_pokemon", "second_pokemon", "winner"]:
			combats[col] = combats[col].map(normalize_name)

		combats.to_csv(DATA_PROC / "combats.csv", index=False)

		# Cálculo de vitórias por pokémon
		wins = combats.groupby("winner").size().rename("wins").reset_index().rename(columns={"winner": "name"})
		# Derrotas: quem perdeu quando o vencedor era o primeiro pokémon
		losers_first = combats[combats["winner"] == combats["first_pokemon"]]["second_pokemon"].value_counts()
		# Derrotas: quem perdeu quando o vencedor era o segundo pokémon
		losers_second = combats[combats["winner"] == combats["second_pokemon"]]["first_pokemon"].value_counts()
		# Soma as derrotas dos dois cenários e gera uma série única
		losses = (losers_first.add(losers_second, fill_value=0)).rename("losses").reset_index().rename(columns={"index": "name"})

		# Junta vitórias e derrotas em uma mesma tabela
		stats = pd.merge(wins, losses, on="name", how="outer").fillna(0)
		stats["total_combats"] = stats["wins"] + stats["losses"]
		stats["win_rate"] = (stats["wins"] / stats["total_combats"]).round(4).fillna(0)

		# Enriquecimento com atributos (tipos e stats de batalha)
		if not attrs.empty:
			stats = stats.merge(attrs[["id", "name", "types", "attack", "defense", "hp", "speed"]], on="name", how="left")

		# Ordena por taxa de vitória e número de vitórias
		stats.sort_values(["win_rate", "wins"], ascending=[False, False], inplace=True)
		stats.to_csv(DATA_PROC / "pokemon_stats.csv", index=False)
		# Exporta rankings auxiliares (top 10 vencedores e perdedores)
		stats.nlargest(10, ["wins"]).to_csv(DATA_PROC / "top10_winners.csv", index=False)
		stats.nlargest(10, ["losses"]).to_csv(DATA_PROC / "top10_losers.csv", index=False)

	# Distribuição de pokémons por tipo
	if not attrs.empty:
		by_type = attrs.assign(type=attrs["types"].str.split("/")).explode("type").groupby("type").size().rename("count").reset_index()
		by_type.to_csv(DATA_PROC / "pokemon_by_type.csv", index=False)

	return {
		"pokemon": DATA_PROC / "pokemon.csv",
		"combats": DATA_PROC / "combats.csv",
		"stats": DATA_PROC / "pokemon_stats.csv",
		"by_type": DATA_PROC / "pokemon_by_type.csv",
	}


def run() -> None:
	"""Executa o ETL completo (extração + transformação) e imprime um resumo.

	Esta função é usada como ponto de entrada quando o arquivo é executado
	diretamente (`python -m src.etl` ou similar).
	"""
	raw = extract_all()
	paths = transform(raw)
	print("ETL concluído:")
	for k, v in paths.items():
		if v.exists():
			print(f"- {k}: {v}")


if __name__ == "__main__":
	run()
