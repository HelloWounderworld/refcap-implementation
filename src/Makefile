.PHONY: test test-fast test-int test-e2e cov scratch

test-fast:            ## T0 — lógica pura, segundos
	pytest tests/unit -q

test-int:             ## T0 + T1
	pytest tests/unit tests/integration -q

test-e2e:             ## T2 — modelos reais (exige GPU + micro_corpus + ffmpeg)
	pytest tests/e2e -m "e2e" -q

test:                 ## loop padrão (rápido)
	pytest

cov:                  ## cobertura das camadas rápidas
	pytest tests/unit tests/integration --cov --cov-report=term-missing

scratch:              ## roda um scratchpad:  make scratch F=scratch/scratch_construct.py
	python $(F)
