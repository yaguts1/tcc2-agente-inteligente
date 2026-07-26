"""Garante um `config.h` para o build.

`config.h` guarda credenciais e é git-ignored, então em máquina limpa (e na CI)
ele não existe e o build falharia com "No such file or directory" — um erro que
não diz o que fazer.

A cópia gerada aqui serve para COMPILAR e nada mais: os valores são os do
exemplo, sem rede real e sem token. Quem for gravar num dispositivo edita o
`config.h` de verdade, e este script não o sobrescreve.
"""

import shutil
from pathlib import Path

Import("env")  # noqa: F821 - injetado pelo PlatformIO

pasta = Path(env.subst("$PROJECT_SRC_DIR"))  # noqa: F821
config = pasta / "config.h"
exemplo = pasta / "config.example.h"

if not config.exists():
    if not exemplo.exists():
        raise SystemExit(f"nem config.h nem config.example.h em {pasta}")
    shutil.copyfile(exemplo, config)
    print(f"[build] config.h ausente; copiado de {exemplo.name} (valores de exemplo)")
