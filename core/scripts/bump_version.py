import subprocess
import re
from pathlib import Path


"""
MAJOR (quebra tudo)
-------------------------------------------------------------------
Usado quando ocorre uma mudança que quebra compatibilidade
com versões anteriores (breaking changes). Normalmente exige
ajustes no código de quem usa o sistema.

Exemplo:
1.0.0 → 2.0.0

Situações típicas de MAJOR:
- Renomear ou remover funções essenciais.
- Alterar comportamento de APIs.
- Alterar estrutura de banco de dados sem migração compatível.
- Mudar pastas principais, caminhos críticos ou URLs-base.

-------------------------------------------------------------------

MINOR (novas features)
-------------------------------------------------------------------
Incrementado quando algo novo é adicionado, mas NADA quebra.
É a versão mais comum ao adicionar melhorias ou funcionalidades.

Exemplo:
1.2.0 → 1.3.0

Situações típicas de MINOR:
- Criar uma nova view.
- Adicionar novas funcionalidades (ex: upload de avatar).
- Criar novos endpoints ou páginas.
- Melhorias nas telas existentes sem alterar funcionamento atual.

Exemplos reais do seu projeto:
- `refactor: mover funções do perfil para profile_views`
  (mudança estrutural, mas sem quebra → MINOR)

- `feat: atualizar imagem padrão do dashboard`
  (é um novo “featurezinho” visual → MINOR)

-------------------------------------------------------------------

PATCH (correções)
-------------------------------------------------------------------
Usado para pequenas correções, sem adicionar features e
sem alterar comportamento existente. Ideal para ajustes pontuais.

Exemplo:
1.3.0 → 1.3.1

Situações típicas de PATCH:
- Corrigir um bug.
- Ajuste de CSS.
- Correção de uma URL quebrada.
- Ajuste em lógica sem mudança de funcionalidade.

Exemplos:
- `fix: corrigir erro no carregamento de avatar`
- `fix: corrigir typo na rota de cadastro`

-------------------------------------------------------------------

Exemplos de commits aplicando na prática:
-------------------------------------------------------------------
feat!: remover método legacy de autenticação e substituir por JWT moderno
→ quebra compatibilidade, exige atualização → **MAJOR**

refactor: mover funções do perfil para profile_views  
→ mudança de estrutura interna, sem quebra → **MINOR**

docs: atualizar README com nova organização  
→ apenas documentação → **PATCH**

feat: atualizar imagem padrão do dashboard  
→ pequena nova feature → **MINOR**

"""

VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"

def get_current_version():
    with open(VERSION_FILE, "r") as f:
        return f.read().strip()

def write_version(version):
    with open(VERSION_FILE, "w") as f:
        f.write(version)

def bump_version(version, bump_type):
    major, minor, patch = map(int, version.split("."))

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1

    return f"{major}.{minor}.{patch}"

def analyze_commits():
    # commits desde a última tag
    log = subprocess.check_output(
        ["git", "log", "--pretty=format:%s", "HEAD"],
        text=True
    )

    bump = "patch"  # padrão

    for msg in log.split("\n"):
        if "BREAKING CHANGE" in msg:
            return "major"
        if msg.startswith("feat:"):
            bump = "minor"
        if msg.startswith("fix:") and bump != "minor":
            bump = "patch"

    return bump

def main():
    current = get_current_version()
    bump_type = analyze_commits()
    new_version = bump_version(current, bump_type)

    write_version(new_version)

    print(f"Versão atualizada: {current} → {new_version}")

if __name__ == "__main__":
    main()
