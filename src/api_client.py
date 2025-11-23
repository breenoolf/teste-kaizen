"""Cliente da API Pokémon.

Este módulo encapsula toda a comunicação com a API REST de Pokémons,
incluindo:

- Carregamento de configurações a partir de variáveis de ambiente.
- Autenticação via JWT no endpoint `/login`.
- Paginação dos endpoints `/pokemon`, `/pokemon/{id}` e `/combats`.
- Tratamento básico de erros, incluindo retry em caso de `429` (rate limit)
	e renovação de token em caso de `401` (não autorizado).

Ele é utilizado tanto pelo ETL quanto por scripts auxiliares.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
import time
from typing import Dict, Iterable, Iterator, List, Optional

import requests
from dotenv import load_dotenv


@dataclass
class ApiConfig:
	"""Configurações necessárias para acessar a API.

	A configuração é carregada a partir das variáveis de ambiente,
	geralmente definidas no arquivo `.env`:

	- `BASE_URL`: endereço base da API (sem a barra final).
	- `API_USERNAME` / `API_PASSWORD`: credenciais para login.
	- `per_page_*`: tamanhos de página padrão para paginação.
	- `max_combats`: limite máximo de combates a serem baixados no ETL.
	"""
	base_url: str
	username: str
	password: str
	per_page_pokemon: int = 50
	per_page_combats: int = 100
	max_combats: int = 5000

	@staticmethod
	def from_env() -> "ApiConfig":
		"""Cria uma instância de `ApiConfig` lendo variáveis de ambiente.

		Utiliza `python-dotenv` para carregar o conteúdo do arquivo `.env`
		antes de buscar os valores.
		"""
		load_dotenv(override=True)
		base_url = os.getenv("BASE_URL")
		if not base_url:
			raise RuntimeError("BASE_URL not set")
		cfg = ApiConfig(
			base_url=base_url.rstrip("/"),
			username=os.getenv("API_USERNAME") or os.getenv("USERNAME") or "",
			password=os.getenv("API_PASSWORD") or os.getenv("PASSWORD") or "",
		)
		mc = os.getenv("MAX_COMBATS")
		if mc and mc.isdigit():
			cfg.max_combats = int(mc)
		return cfg


class ApiClient:
	"""Cliente HTTP para a API Pokémon.

	Responsável por:
	- Realizar login e armazenar o token JWT.
	- Montar cabeçalhos de autenticação.
	- Paginar respostas de `/pokemon` e `/combats`.
	- Repetir requisições em casos específicos (401 e 429).
	"""

	def __init__(self, cfg: ApiConfig):
		# Armazena as configurações e inicializa o token em branco
		self.cfg = cfg
		self._token: Optional[str] = None
		# Número máximo de tentativas em caso de erros tratáveis
		self.max_retries = 5

	def _headers(self) -> Dict[str, str]:
		"""Monta os cabeçalhos HTTP com o token JWT atual.

		Caso ainda não haja token carregado, realiza o login automaticamente.
		"""
		if not self._token:
			self.login()
		return {"Authorization": f"Bearer {self._token}"}

	def login(self) -> None:
		"""Realiza autenticação na API e armazena o token JWT interno.

		Se a resposta não contiver um campo `access_token`, lança um erro
		para deixar claro que algo inesperado aconteceu na API.
		"""
		url = f"{self.cfg.base_url}/login"
		resp = requests.post(url, json={"username": self.cfg.username, "password": self.cfg.password}, timeout=30)
		resp.raise_for_status()
		self._token = resp.json().get("access_token")
		if not self._token:
			raise RuntimeError("No access_token in login response")

	def _request(self, method: str, url: str, **kwargs) -> requests.Response:
		"""Envia uma requisição HTTP com política de retry.

		Estratégia:
		- Em caso de 401 (não autorizado), tenta renovar o token e refazer
		  a requisição uma vez.
		- Em caso de 429 (muitas requisições), aguarda um tempo (Retry-After
		  ou backoff exponencial) antes de tentar novamente.
		"""
		for attempt in range(self.max_retries):
			resp = requests.request(method, url, **kwargs)
			if resp.status_code == 401 and attempt < self.max_retries - 1:
				# Token expirado ou inválido: renova e tenta novamente
				self.login()
				kwargs["headers"] = self._headers()
				continue
			if resp.status_code == 429 and attempt < self.max_retries - 1:
				# Rate limit atingido: espera antes de tentar novamente
				retry_after = resp.headers.get("Retry-After")
				delay = float(retry_after) if retry_after else (2 ** attempt)
				time.sleep(delay)
				continue
			return resp
		return resp

	def get_pokemon_page(self, page: int, per_page: Optional[int] = None) -> Dict:
		"""Busca uma página de pokémons básicos (`/pokemon`).

		Retorna o JSON completo da página, incluindo lista de pokémons
		(`pokemons`), página atual (`page`), `per_page` e `total`.
		"""
		pp = per_page or self.cfg.per_page_pokemon
		url = f"{self.cfg.base_url}/pokemon"
		resp = self._request("GET", url, headers=self._headers(), params={"page": page, "per_page": pp}, timeout=60)
		resp.raise_for_status()
		return resp.json()

	def get_pokemon_attributes(self, pokemon_id: int) -> Dict:
		"""Busca os atributos completos de um pokémon específico.

		Chama o endpoint `/pokemon/{pokemon_id}` e devolve o JSON com
		todos os stats, tipos, geração, etc.
		"""
		url = f"{self.cfg.base_url}/pokemon/{pokemon_id}"
		resp = self._request("GET", url, headers=self._headers(), timeout=60)
		resp.raise_for_status()
		return resp.json()

	def iter_all_pokemon(self) -> Iterator[Dict]:
		"""Itera por todos os pokémons da API, página a página.

		Esconde a lógica de paginação do chamador, fazendo `yield` de
		cada registro retornado em `pokemons` até percorrer o total.
		"""
		page = 1
		while True:
			data = self.get_pokemon_page(page)
			pokemons = data.get("pokemons") or []
			for p in pokemons:
				yield p
			total = data.get("total") or 0
			per_page = data.get("per_page") or self.cfg.per_page_pokemon
			if page * per_page >= total:
				break
			page += 1

	def get_combats_page(self, page: int, per_page: Optional[int] = None) -> Dict:
		"""Busca uma página de combates (`/combats`)."""
		pp = per_page or self.cfg.per_page_combats
		url = f"{self.cfg.base_url}/combats"
		resp = self._request("GET", url, headers=self._headers(), params={"page": page, "per_page": pp}, timeout=60)
		resp.raise_for_status()
		return resp.json()

	def iter_all_combats(self) -> Iterator[Dict]:
		"""Itera por combates até percorrer todas as páginas ou atingir o limite.

		O limite de combates retornados é controlado por `max_combats` na
		configuração, o que evita rodadas muito demoradas durante o ETL.
		"""
		page = 1
		while True:
			data = self.get_combats_page(page)
			combats = data.get("combats") or []
			for c in combats:
				yield c
				# Corta a iteração se já alcançou o máximo configurado
				if page * (data.get("per_page") or self.cfg.per_page_combats) >= self.cfg.max_combats:
					return
			total = data.get("total") or 0
			per_page = data.get("per_page") or self.cfg.per_page_combats
			if page * per_page >= total:
				break
			page += 1
