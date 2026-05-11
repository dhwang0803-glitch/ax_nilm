import { setupWorker } from "msw/browser";
import { handlers } from "../../tests/fixtures/handlers";

export const worker = setupWorker(...handlers);
