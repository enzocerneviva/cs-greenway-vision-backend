# Avaliação do classificador de vegetação

Gerado por `python -m data.mapillary.evaluate_classifier --report ...`. Mede o modelo sem treiná-lo nem alterá-lo. Como ler cada seção: ver o docstring do script.

```text
Imagens rotuladas: 648 | classes: {'LOW': 199, 'MEDIUM': 65, 'HIGH': 384}
Sequências: 7 | blocos de 20 fotos consecutivas: 36

=== 1 e 2. Nota do modelo: split aleatório x por blocos de tempo; recorte x imagem inteira ===

[crop | CV aleatório]
  acurácia 88.0% | F1 macro 0.75 | recall LOW 91% MEDIUM 32% HIGH 96%
  matriz de confusão (linhas=real, colunas=previsto; ordem ['LOW', 'MEDIUM', 'HIGH']):
    LOW   [181   4  14]
    MEDIUM[ 7 21 37]
    HIGH  [  1  15 368]

[crop | CV por blocos]
  acurácia 80.9% | F1 macro 0.57 | recall LOW 82% MEDIUM 0% HIGH 94%
  matriz de confusão (linhas=real, colunas=previsto; ordem ['LOW', 'MEDIUM', 'HIGH']):
    LOW   [163   2  34]
    MEDIUM[ 8  0 57]
    HIGH  [ 15   8 361]

[squash | CV aleatório]
  acurácia 88.3% | F1 macro 0.76 | recall LOW 91% MEDIUM 37% HIGH 96%
  matriz de confusão (linhas=real, colunas=previsto; ordem ['LOW', 'MEDIUM', 'HIGH']):
    LOW   [181   7  11]
    MEDIUM[ 5 24 36]
    HIGH  [  3  14 367]

[squash | CV por blocos]
  acurácia 82.1% | F1 macro 0.58 | recall LOW 81% MEDIUM 0% HIGH 96%
  matriz de confusão (linhas=real, colunas=previsto; ordem ['LOW', 'MEDIUM', 'HIGH']):
    LOW   [162   6  31]
    MEDIUM[ 6  0 59]
    HIGH  [  9   5 370]

=== Só a sequência grande (mesma estrada: sem o atalho 'qual estrada é esta?') ===
  sequência YNKVyjAF…: 500 fotos, classes {'LOW': 53, 'MEDIUM': 63, 'HIGH': 384}

[dentro de uma estrada só | CV por blocos]
  acurácia 80.6% | F1 macro 0.51 | recall LOW 42% MEDIUM 6% HIGH 98%
  matriz de confusão (linhas=real, colunas=previsto; ordem ['LOW', 'MEDIUM', 'HIGH']):
    LOW   [22  0 31]
    MEDIUM[ 5  4 54]
    HIGH  [  5   2 377]

=== 4. A confiança do modelo distingue acerto de erro? (recorte, CV por blocos) ===
  confiança média quando ACERTA: 0.67 | quando ERRA: 0.52
  só confiança >= 0.5: mantém 78% das fotos, acurácia 88.0%
  só confiança >= 0.6: mantém 56% das fotos, acurácia 91.8%
  só confiança >= 0.7: mantém 35% das fotos, acurácia 96.5%
  só confiança >= 0.8: mantém 21% das fotos, acurácia 98.5%

=== 3. Pré-filtro de cor (< 5 % de verde vira LOW sem passar pelo modelo) ===
  LOW    verde mediano   7.4% | abaixo de 5 %: 56 de 199 (28%)
  MEDIUM verde mediano  10.1% | abaixo de 5 %: 9 de 65 (14%)
  HIGH   verde mediano  13.7% | abaixo de 5 %: 4 de 384 (1%)

=== 5. Modelo atual nas fotos reais de campo (data/images-real-road) ===
  recorte (atual): 15 fotos -> previsões {'LOW': 13, 'MEDIUM': 0, 'HIGH': 2} | acertos vs. gabarito: 13/15
  imagem inteira: 15 fotos -> previsões {'LOW': 10, 'MEDIUM': 0, 'HIGH': 5} | acertos vs. gabarito: 10/15
  (atenção: o modelo atual foi treinado com recorte; 'imagem inteira' aqui é só um teste de sensibilidade)
```
