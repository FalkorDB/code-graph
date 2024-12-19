export function getEnvVariables() {
    const { SECRET_TOKEN, BACKEND_URL } = process.env

    if (!BACKEND_URL) {
        throw new Error("Environment variable BACKEND_URL must be set");
    }
    if (!SECRET_TOKEN) {
        throw new Error("Environment variable SECRET_TOKEN must be set");
    }

    return { url: BACKEND_URL, token: SECRET_TOKEN };
}