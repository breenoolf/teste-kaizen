"""Script de smoke test para a API Pokémon.

Este módulo faz um fluxo mínimo para validar o acesso à API:

1. Carrega variáveis de ambiente do arquivo `.env`.
2. Realiza login em `/login` para obter o token JWT.
3. Chama o endpoint `/pokemon` usando o token.
4. Salva a resposta em `data/raw/pokemon.json` para inspeção.

É útil para testar rapidamente se as credenciais e a URL da API
estão corretas antes de rodar o ETL completo.
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv


def get_env(name: str, default: Optional[str] = None) -> str:
	"""Lê uma variável de ambiente obrigatória.

	Se a variável não existir e nenhum valor padrão for informado,
	dispara um erro para deixar claro o problema de configuração.
	"""
	val = os.getenv(name, default)
	if val is None:
		raise RuntimeError(f"Missing required env var: {name}")
	return val.strip()


def get_token(base_url: str, username: str, password: str) -> str:
	"""Realiza login na API e retorna o token JWT.

	Envia um POST para `/login` com usuário e senha.
	Em caso de erro 4xx, imprime o corpo da resposta para facilitar
	debug e depois levanta uma exceção.
 
	Retorna o valor do campo `access_token` (ou equivalente).
	"""
	url = f"{base_url}/login"
	resp = requests.post(
		url,
		json={"username": username, "password": password},
		timeout=30,
	)
	if resp.status_code >= 400:
		# Mostra detalhes da resposta em caso de falha de autenticação
		try:
			print("Login error:", resp.status_code, resp.text)
		except Exception:
			pass
	resp.raise_for_status()
	payload: Dict[str, Any] = resp.json()
	token = payload.get("access_token") or payload.get("token") or payload.get("jwt")
	if not token:
		raise RuntimeError(f"Token not found in response: {payload}")
	return token


def fetch_pokemon(base_url: str, token: str) -> Any:
	"""Obtém uma página de pokémons da API.

	Utiliza o token JWT informado no cabeçalho Authorization.
	Aqui o objetivo é apenas verificar se a chamada autenticada
	está funcionando e capturar uma amostra de dados.
	"""
	url = f"{base_url}/pokemon"
	headers = {"Authorization": f"Bearer {token}"}
	resp = requests.get(url, headers=headers, timeout=60)
	resp.raise_for_status()
	return resp.json()


def main() -> None:
	"""Executa o fluxo completo do smoke test.

	1. Lê BASE_URL, API_USERNAME e API_PASSWORD do `.env`.
	2. Faz o login na API e obtém o token JWT.
	3. Chama `/pokemon` usando o token.
	4. Salva o JSON retornado em `data/raw/pokemon.json`.
	"""
	# Carrega variáveis definidas no arquivo .env
	load_dotenv(override=True)
	base_url = get_env("BASE_URL").rstrip("/")
	username = get_env("API_USERNAME")
	password = get_env("API_PASSWORD")
	print(f"Debug: using username='{username}', pwd_len={len(password)}")

	# Obtém o token JWT e busca uma amostra de pokémons
	token = get_token(base_url, username, password)
	data = fetch_pokemon(base_url, token)

	# Garante que a pasta de saída exista e salva o JSON bruto
	out_dir = Path("data/raw")
	out_dir.mkdir(parents=True, exist_ok=True)
	out_file = out_dir / "pokemon.json"
	out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

	# Exibe um resumo no console
	count = len(data) if isinstance(data, list) else None
	if count is not None:
		print(f"OK: fetched {count} records  {out_file}")
	else:
		print(f"OK: data saved  {out_file}")


if __name__ == "__main__":
	main()
