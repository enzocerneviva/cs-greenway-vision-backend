# Regra desta camada: os repositories NÃO fazem commit. Eles só montam/enviam
# as operações (add, flush, delete) dentro da transação da Session; quem decide
# quando confirmar (commit) ou desfazer (rollback) é o caso de uso que chama —
# o service, ou a rota quando ela não passa por um service. Assim uma operação
# do negócio que mexe em várias tabelas é "tudo ou nada".
