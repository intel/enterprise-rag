/// <reference types="vite/client" />

declare module "*.scss" {
  const content: string;
  export default content;
}

interface Window {
  env: Record<string, string>;
}
