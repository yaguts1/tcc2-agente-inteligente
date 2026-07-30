  import { createRoot } from "react-dom/client";
  import { ThemeProvider } from "next-themes";
  import App from "./App.tsx";
  import "./styles/globals.css";

  createRoot(document.getElementById("root")!).render(
    /*
      O modo escuro estava escrito e nao ligado: `globals.css` tem
      `@custom-variant dark` e o bloco `.dark` inteiro, e nada aplicava a classe.
      O unico `useTheme` do projeto (em `ui/sonner.tsx`) falava com provider
      nenhum.

      `attribute="class"` porque e o que a folha de estilo espera
      (`&:is(.dark *)`). `defaultTheme="system"` respeita o `prefers-color-scheme`
      do aparelho, entao o tablet da ala noturna ja abre escuro sem ninguem
      configurar nada.

      Fica AQUI e nao dentro do `App`: o next-themes injeta um script que aplica
      a classe antes da primeira pintura, e montar o provider mais fundo
      produziria um flash branco a cada carregamento — que num quarto escuro as
      3h e exatamente o que se esta tentando evitar.
    */
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      storageKey="upp-tema"
      disableTransitionOnChange
    >
      <App />
    </ThemeProvider>,
  );
