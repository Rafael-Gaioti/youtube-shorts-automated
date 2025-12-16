"""
Script de Verificacao de Dependencias
Verifica se todas as dependencias necessarias estao instaladas.
"""

import sys
import subprocess
import shutil
from pathlib import Path
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_python_version():
    """Verifica versão do Python."""
    print("[*] Verificando Python...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 10:
        print(f"  [OK] Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"  [ERRO] Python {version.major}.{version.minor} (requer 3.10+)")
        return False

def check_pip_package(package_name: str) -> bool:
    """Verifica se um pacote Python está instalado."""
    try:
        __import__(package_name.replace('-', '_'))
        return True
    except ImportError:
        return False

def check_python_packages():
    """Verifica pacotes Python essenciais."""
    print("\n[*] Verificando pacotes Python...")

    packages = {
        'yaml': 'pyyaml',
        'dotenv': 'python-dotenv',
        'anthropic': 'anthropic',
        'faster_whisper': 'faster-whisper',
        'torch': 'torch'
    }

    all_installed = True
    for import_name, package_name in packages.items():
        if check_pip_package(import_name):
            print(f"  [OK] {package_name}")
        else:
            print(f"  [FALTA] {package_name}")
            all_installed = False

    if not all_installed:
        print("\n[!] Instale as dependencias com:")
        print("   pip install -r requirements.txt")

    return all_installed

def check_system_command(command: str) -> bool:
    """Verifica se um comando do sistema existe."""
    return shutil.which(command) is not None

def check_external_tools():
    """Verifica ferramentas externas."""
    print("\n[*] Verificando ferramentas externas...")

    tools = {
        'yt-dlp': 'Download de videos',
        'ffmpeg': 'Processamento de video',
        'ffprobe': 'Analise de video'
    }

    all_installed = True
    for tool, description in tools.items():
        if check_system_command(tool):
            # Tentar obter versão
            try:
                result = subprocess.run(
                    [tool, '--version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                version = result.stdout.split('\n')[0]
                print(f"  [OK] {tool} - {version[:50]}")
            except:
                print(f"  [OK] {tool}")
        else:
            print(f"  [FALTA] {tool} - ({description})")
            all_installed = False

    if not all_installed:
        print("\n[!] Instrucoes de instalacao:")
        print("\n  yt-dlp:")
        print("    pip install yt-dlp")
        print("    OU baixe de: https://github.com/yt-dlp/yt-dlp/releases")

        print("\n  FFmpeg:")
        print("    Windows: choco install ffmpeg")
        print("    OU baixe de: https://ffmpeg.org/download.html")
        print("    Linux: sudo apt install ffmpeg")
        print("    macOS: brew install ffmpeg")

    return all_installed

def check_cuda():
    """Verifica CUDA para GPU."""
    print("\n[*] Verificando suporte GPU (CUDA)...")

    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            cuda_version = torch.version.cuda
            print(f"  [OK] CUDA {cuda_version}")
            print(f"  [OK] GPU: {gpu_name}")
            return True
        else:
            print("  [AVISO] CUDA nao disponivel (processamento sera em CPU)")
            print("  [!] Para usar GPU, instale CUDA Toolkit:")
            print("     https://developer.nvidia.com/cuda-downloads")
            return False
    except ImportError:
        print("  [AVISO] PyTorch nao instalado (nao e possivel verificar CUDA)")
        return False

def check_env_file():
    """Verifica arquivo .env."""
    print("\n[*] Verificando configuracao...")

    env_path = Path('.env')
    env_example = Path('.env.example')

    if env_path.exists():
        print(f"  [OK] {env_path}")

        # Verificar se API key está configurada
        with open(env_path, 'r') as f:
            content = f.read()
            if 'your_anthropic_api_key_here' in content or 'your_' in content:
                print("  [AVISO] API Keys parecem nao estar configuradas")
                print("  [!] Edite .env e adicione suas chaves reais")
            else:
                print("  [OK] API Keys configuradas")
        return True
    else:
        print(f"  [FALTA] {env_path}")
        if env_example.exists():
            print(f"  [!] Copie {env_example} para .env e configure as chaves")
            print(f"     cp .env.example .env")
        return False

def check_directory_structure():
    """Verifica estrutura de diretorios."""
    print("\n[*] Verificando estrutura de diretorios...")

    required_dirs = [
        'config/prompts',
        'data/raw',
        'data/transcripts',
        'data/analysis',
        'data/output',
        'models',
        'logs'
    ]

    all_exist = True
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists():
            print(f"  [OK] {dir_path}/")
        else:
            print(f"  [FALTA] {dir_path}/")
            all_exist = False

    if not all_exist:
        print("\n  [!] Crie os diretorios faltantes:")
        print("     mkdir -p " + " ".join(required_dirs))

    return all_exist

def main():
    """Função principal."""
    print("=" * 60)
    print("  VERIFICAÇÃO DE DEPENDÊNCIAS - YouTube Shorts Automation")
    print("=" * 60)

    results = []

    results.append(("Python", check_python_version()))
    results.append(("Pacotes Python", check_python_packages()))
    results.append(("Ferramentas Externas", check_external_tools()))
    results.append(("GPU/CUDA", check_cuda()))
    results.append(("Configuração", check_env_file()))
    results.append(("Estrutura de Diretórios", check_directory_structure()))

    print("\n" + "=" * 60)
    print("  RESUMO")
    print("=" * 60)

    for name, status in results:
        icon = "[OK]" if status else "[FALTA]"
        print(f"  {icon} {name}")

    all_ok = all(status for _, status in results)

    if all_ok:
        print("\n[SUCCESS] Todas as dependencias estao instaladas!")
        print("Voce pode comecar a usar o sistema.")
    else:
        print("\n[AVISO] Algumas dependencias estao faltando.")
        print("Siga as instrucoes acima para instala-las.")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
