-- Garante que a instalação tenha ao menos um administrador.
--
-- A regra "o primeiro usuário vira admin" só passou a valer no cadastro a
-- partir da introdução dos papéis. Numa instalação que já existia, TODOS os
-- usuários foram criados antes disso e ficaram com o default `staff` do
-- schema — ou seja, ao atualizar, o sistema ficaria sem nenhum admin e as
-- operações administrativas (backup, importação, gestão de usuários) seriam
-- permanentemente inacessíveis, sem caminho de recuperação pela interface.
--
-- Promove a conta mais antiga, que é a de quem instalou o sistema. Só age se
-- não houver nenhum admin ativo, então é idempotente e não interfere em
-- instalações que já resolveram isso.

UPDATE users
   SET role = 'admin'
 WHERE username = (SELECT username FROM users ORDER BY created_at, username LIMIT 1)
   AND NOT EXISTS (SELECT 1 FROM users WHERE role = 'admin' AND ativo = 1);
