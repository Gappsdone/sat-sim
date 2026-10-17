import { defineConfig, loadEnv, type Plugin } from "vite";
import { viteStaticCopy } from "vite-plugin-static-copy";

const developmentDocument = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#061018" />
    <title>ISS Systems Console</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>`;

function virtualDocument(): Plugin {
  return {
    name: "virtual-document",
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        if (request.url !== "/") {
          next();
          return;
        }
        response.setHeader("Content-Type", "text/html");
        response.end(developmentDocument);
      });
    },
    generateBundle(_options, bundle) {
      const entry = Object.values(bundle).find(
        (item) => item.type === "chunk" && item.isEntry,
      );
      if (!entry || entry.type !== "chunk") {
        this.error("frontend entry chunk was not generated");
      }
      const stylesheet = Object.values(bundle).find(
        (item) => item.type === "asset" && item.fileName.endsWith(".css"),
      );
      const styleTag = stylesheet
        ? `<link rel="stylesheet" href="/${stylesheet.fileName}" />`
        : "";
      const productionDocument = developmentDocument
        .replace("</head>", `    ${styleTag}\n  </head>`)
        .replace('/src/main.ts', `/${entry.fileName}`);
      this.emitFile({
        type: "asset",
        fileName: "index.html",
        source: productionDocument,
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, process.cwd(), "");
  const allowedHosts = (environment.VITE_ALLOWED_HOSTS ?? "")
    .split(",")
    .map((host) => host.trim())
    .filter(Boolean);

  return {
    plugins: [
      virtualDocument(),
      viteStaticCopy({
        targets: [
          {
            src: "node_modules/cesium/Build/Cesium/{Assets,ThirdParty,Widgets,Workers}",
            dest: "cesium",
          },
        ],
      }),
    ],
    define: { CESIUM_BASE_URL: JSON.stringify("/cesium") },
    server: {
      host: "0.0.0.0",
      allowedHosts,
      port: 5173,
      proxy: {
        "/api": { target: "http://127.0.0.1:8000", ws: true },
      },
    },
    build: {
      target: "es2022",
      rollupOptions: { input: "src/main.ts" },
    },
  };
});
