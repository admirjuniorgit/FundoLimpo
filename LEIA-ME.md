# FundoLimpo

Remove o fundo da webcam **sem fundo verde**, em qualquer placa de vídeo (NVIDIA, AMD ou Intel) ou até só no
processador, e entrega o resultado na **própria câmera virtual do app — "FundoLimpo Camera"** — que aparece como
webcam no **OBS, Streamlabs, Discord, Zoom, Teams, Meet** e em qualquer programa que use webcam. **Não precisa do OBS.**

## Como funciona
1. A webcam é lida pelo OpenCV.
2. O modelo **Robust Video Matting** (RVM, MobileNetV3, `modelo/rvm_mobilenetv3_fp32.onnx`) recorta a pessoa com
   transparência real (fios de cabelo inclusive) e **memória entre quadros** — a borda não treme.
3. Roda no **ONNX Runtime + DirectML** (qualquer GPU DirectX 12 no Windows). Sem GPU compatível, usa o processador.
4. O fundo vira desfoque, uma imagem ou uma cor sólida (o verde serve de chroma key, se quiser).
5. A imagem sai pela **FundoLimpo Camera** (`camera\x64\fundolimpo_cam.dll`): um dispositivo de vídeo DirectShow,
   o mesmo tipo de câmera virtual que o OBS e o NVIDIA Broadcast usam.

## Usar
1. Instale o [Python 3.12](https://www.python.org/downloads/) (marque "Add python.exe to PATH").
2. Rode `instalar.bat` uma vez. No final ele instala a câmera (o Windows pede permissão de administrador).
3. Rode `abrir.bat`. **Deixe o FundoLimpo aberto** enquanto usa a câmera.
4. **OBS / Streamlabs:** adicione uma fonte **"Dispositivo de captura de vídeo"** e escolha **"FundoLimpo Camera"**.
   **Discord / Teams / Meet / Zoom:** escolha "FundoLimpo Camera" nas configurações de vídeo.

## Gerar o instalador (para você usar e para mandar para outras pessoas)
Rode **`gerar-instalador.bat`**. Ele empacota o app (PyInstaller), instala o Inno Setup sozinho se faltar (via winget)
e cria **`dist\instalador\FundoLimpo-Setup-<versão>.exe`** — um arquivo único, sem precisar de Python.

O Setup instala em *Arquivos de Programas*, cria atalhos (Menu Iniciar e, se marcar, área de trabalho), **registra a
câmera "FundoLimpo Camera"** e aparece em *Configurações → Aplicativos*; desinstalar remove a câmera também.
## Enviar para outras pessoas e atualizar sozinho
- **Link direto do instalador (sempre a última versão):**
  https://github.com/admirjuniorgit/FundoLimpo/releases/latest/download/FundoLimpo-Setup.exe
- Repositório: https://github.com/admirjuniorgit/FundoLimpo (público: código + instaladores nas *Releases*).
- **Atualização automática:** ao abrir, o app instalado consulta a última release. Se houver versão maior, pergunta
  se quer atualizar, baixa o Setup, instala por cima em silêncio e reabre o app (`fundolimpo/updater.py`).
  Funciona a partir da versão 1.2.0 (a primeira com o atualizador).

### Commitar mudanças
No Git Bash, dentro da pasta: **`./commit.sh "o que mudou"`** (sem texto, ele pergunta). Na primeira vez ele liga a
pasta ao repositório do GitHub sozinho.

### Lançar uma versão nova
1. Mude `VERSION` em `fundolimpo/app.py` (ex.: `1.2.0` → `1.3.0`). Tem que subir, senão ninguém atualiza.
2. Rode `./commit.sh "o que mudou nesta versão"`.
3. O GitHub Actions (`.github/workflows/release.yml`) gera o instalador no Windows e publica a release `vX.Y.Z` com
   `FundoLimpo-Setup.exe` em ~10 min. A mensagem do commit vira a nota da versão que o usuário vê.

Para gerar o instalador no seu PC (testar antes de publicar), continue usando o `gerar-instalador.bat`.

Ao abrir o Setup, o Windows pode mostrar *"O Windows protegeu o computador"* (o instalador não tem assinatura digital):
clique em **Mais informações → Executar assim mesmo**. Para sumir com esse aviso é preciso um certificado de
assinatura de código.

Obs.: se você usa a versão de desenvolvimento (`abrir.bat`) e a instalada no mesmo PC, a câmera fica registrada na
última que foi instalada; a outra mostra o botão "Instalar câmera" para trocar.

Dicas:
- Abra o FundoLimpo **antes** de adicionar a câmera no OBS/Streamlabs. Se trocar a resolução no FundoLimpo,
  desative e reative a fonte no OBS para ele pegar o tamanho novo.
- Se mudar a pasta do app de lugar, clique em "Instalar câmera" de novo (o Windows guarda o caminho da DLL).
- Para tirar a câmera do Windows: botão "Remover câmera" no app ou `remover-camera.bat`.
- Testar sem webcam: `.venv\Scripts\python -m fundolimpo.app --teste foto.jpg saida` → `saida.png` e `saida-mascara.png`.

## Ajustes
- **Desempenho**: *Máxima* (placa de vídeo boa), *Equilibrada* (padrão), *Rápida* (PC fraco / só processador).
- **Firmeza da borda**: aumente se sobrar um contorno do fundo em volta de você.
- **Ver máscara**: mostra em preto e branco o que o modelo está recortando (bom para ajustar a luz).
- Luz de frente no rosto e algum contraste com o fundo valem mais que qualquer ajuste.

Configurações: `%APPDATA%\FundoLimpo\settings.json`.

## Câmera virtual (código-fonte)
`camera\codigo-fonte-camera.zip` tem o código da DLL: o [softcam](https://github.com/tshino/softcam) (MIT) com nome
"FundoLimpo Camera", GUID `{C858F59A-A4E6-4E81-9542-2209A8B5AAD6}` e memória compartilhada próprios (não conflita com
outros apps baseados no softcam). `build.sh` recompila com MinGW (64 e 32 bits). A versão 32 bits só serve para
programas antigos de 32 bits; OBS, Streamlabs e Discord são 64 bits.

## Licenças
- Robust Video Matting: **GPL-3.0** (https://github.com/PeterL1n/RobustVideoMatting). Se for distribuir/vender
  o app com esse modelo, o app também precisa ser GPL-3.0 (código aberto). Para um produto fechado, troque o
  modelo por um de licença permissiva (ex.: MediaPipe Selfie Segmentation, Apache-2.0 — qualidade menor no cabelo).
- softcam e DirectShow BaseClasses: MIT. ONNX Runtime: MIT. OpenCV: Apache-2.0. pygrabber: MIT.
