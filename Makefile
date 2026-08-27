# Atajos del proyecto. Cada uno es un comando que se corre a mano con
# frecuencia; nada acá esconde lógica que no esté en el paquete.

VENV := venv/bin

.PHONY: ayuda instalar esquema banco servidor front pruebas propiedades linter verificar limpiar

ayuda:
	@echo "instalar     Instala el paquete y las dependencias de desarrollo"
	@echo "esquema      Aplica las migraciones pendientes"
	@echo "banco        Valida y publica el banco de instancias"
	@echo "servidor     Levanta la API en el puerto 8000"
	@echo "front        Levanta la interfaz en el puerto 5173"
	@echo "pruebas      Corre la suite completa"
	@echo "propiedades  Corre sólo las propiedades formales del marco"
	@echo "linter       Revisa el estilo del backend y del frontend"
	@echo "verificar    Linter + pruebas + build del frontend"
	@echo "limpiar      Borra artefactos de build y caches"

instalar:
	$(VENV)/pip install -e ".[dev,analisis]"
	cd frontend && npm install

esquema:
	$(VENV)/alembic upgrade head

banco:
	$(VENV)/cps banco validar
	$(VENV)/cps banco sembrar --forzar

servidor:
	$(VENV)/uvicorn cps.api.app:app --reload --port 8000

front:
	cd frontend && npm run dev

pruebas:
	$(VENV)/pytest

propiedades:
	$(VENV)/pytest -m propiedad -v

linter:
	$(VENV)/ruff check src tests scripts
	cd frontend && npx oxlint src

verificar: linter pruebas
	cd frontend && npm run build

limpiar:
	rm -rf .pytest_cache .ruff_cache .hypothesis .coverage htmlcov frontend/dist
	find . -type d -name __pycache__ -not -path "./venv/*" -exec rm -rf {} +
