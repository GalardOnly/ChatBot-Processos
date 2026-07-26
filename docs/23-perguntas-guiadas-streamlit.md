# Perguntas guiadas no Streamlit

Esta etapa leva o banco de perguntas para a interface da PoC.

No chat do Streamlit, a area de perguntas sugeridas agora usa o endpoint `GET /perguntas-audiencia` para carregar perguntas oficiais. O defensor pode filtrar por area, tipo de audiencia e tema antes de enviar a pergunta ao chat.

Tambem existe uma area recolhida de perguntas candidatas. Ela usa a curadoria local de fontes e mostra perguntas ainda nao revisadas, com limite de exibicao. Essas perguntas servem para teste e descoberta, nao como banco oficial do produto.

## Fluxo esperado

1. Subir a API.
2. Subir o Streamlit.
3. Carregar um processo concluido.
4. Abrir a aba `Chat`.
5. Filtrar perguntas oficiais.
6. Clicar em uma pergunta para enviar ao chat.

## Comandos

```powershell
python -m uvicorn preparador_audiencia.main:app --host 127.0.0.1 --port 8910
```

```powershell
python -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

## Decisao

As perguntas oficiais aparecem primeiro porque passaram pelo banco principal. As candidatas ficam separadas para evitar que o defensor confunda material de laboratorio com sugestao revisada.
