// ESLint estava ausente. O `tsc --noEmit` do CI cobre tipos e nao cobre
// nenhuma das classes abaixo — todas elas passam pelo typecheck sem ruido.
//
// O conjunto segue o mesmo critério usado no ruff do backend (ver
// `pyproject.toml`): entram as regras que apontam DEFEITO, ficam de fora as que
// apontam gosto. Formatação não entra — não há prettier aqui e adicioná-lo
// reescreveria o repositório inteiro num diff que esconderia tudo mais.
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';

export default tseslint.config(
  {
    ignores: [
      'dist',
      // `build/` e a saida do vite — bundle minificado. Sem ignorar, ele
      // sozinho responde por 1243 dos 1559 achados e afoga o sinal real.
      'build',
      'node_modules',
      // Gerado por `openapi-typescript` a partir do spec. Editar aqui e
      // perder na proxima geracao; a guarda de contrato vive no CI.
      'src/lib/api-gerada.d.ts',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    plugins: { 'react-hooks': reactHooks },
    rules: {
      // As regras de hooks são a razão principal de o ESLint existir num
      // projeto React: dependência faltando num `useEffect` produz tela com
      // dado velho, que é indistinguível de dado certo até alguém conferir
      // contra o banco. O typecheck não vê nada disso.
      ...reactHooks.configs.recommended.rules,

      // `console.log` com dado de paciente é achado de LGPD, não ruído de
      // estilo: o console do navegador é lido por qualquer um com acesso
      // físico à estação, e a ala inteira compartilha estação.
      // `warn`/`error` seguem permitidos — são para operação, não depuração.
      'no-console': ['error', { allow: ['warn', 'error'] }],

      // `any` desliga o TypeScript no ponto exato em que ele seria útil, e
      // este projeto acabou de ancorar os tipos do front no spec do backend
      // (`src/lib/contrato.ts`). Um `any` no meio do caminho torna a âncora
      // decorativa. Aviso, e não erro: há ocorrências herdadas.
      '@typescript-eslint/no-explicit-any': 'warn',

      // Variável não usada normalmente é resto de refactor — ou o sintoma de
      // que alguém calculou algo e esqueceu de usar, que já aconteceu neste
      // repositório no lado Python (contagem descartada que fazia a tela
      // exibir o número errado). Prefixo `_` continua sendo a saída explícita.
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
  {
    // O service worker roda num escopo global PRÓPRIO (`ServiceWorkerGlobalScope`),
    // não no `window`. Sem declarar `self`, o ESLint acusa nove `no-undef` num
    // arquivo perfeitamente correto — e "adicionar globals" é a correção certa,
    // não desligar a regra, que continua valendo para o resto.
    //
    // `no-console` também sai: o SW não tem UI, e o console do worker é o único
    // canal de diagnóstico quando ele falha em entregar uma notificação.
    files: ['public/**/*.js'],
    languageOptions: {
      globals: { self: 'readonly', clients: 'readonly', caches: 'readonly' },
    },
    rules: { 'no-console': 'off' },
  },
  {
    // Testes: `any` e console são ferramentas legítimas de teste.
    files: ['**/*.test.{ts,tsx}', '**/setupTests.ts'],
    rules: {
      'no-console': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },
);
