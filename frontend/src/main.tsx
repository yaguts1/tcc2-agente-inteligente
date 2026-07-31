  import { createRoot } from "react-dom/client";
  import { ThemeProvider } from "next-themes";
  import App from "./App.tsx";
  import "./styles/globals.css";

  /*
    Registro do service worker — o unico codigo desta aplicacao que roda com a
    aba fechada, e portanto o unico caminho pelo qual um alerta que escala as
    04:00 chega a alguem.

    Falhar aqui NAO pode impedir a aplicacao de subir: o painel funciona
    sozinho, e a notificacao e uma camada sobre ele. Mas tambem nao pode falhar
    calado, que e exatamente o defeito que ele veio corrigir — o beep de
    `useCriticalAlerts` ja desiste em silencio quando o Chrome recusa autoplay.

    O escopo carrega o BASE_URL: sob `/TCC/`, um service worker registrado na
    raiz nao controla as paginas do prefixo, e o `pushManager` fica inacessivel
    sem nenhum erro obvio.
  */
  if ("serviceWorker" in navigator) {
    const base = import.meta.env.BASE_URL || "/";
    navigator.serviceWorker
      .register(`${base}sw.js`, { scope: base })
      .catch((erro) => console.error("[push] service worker nao registrado:", erro));
  }

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
