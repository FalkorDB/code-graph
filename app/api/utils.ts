export function getEnvVariables() {
    const url = process.env.BACKEND_URL
    const token = process.env.SECRET_TOKEN

    if (!url) {
        throw new Error("Environment variable BACKEND_URL must be set");
    }
    if (!token) {
        throw new Error("Environment variable SECRET_TOKEN must be set");
    }

    return { url, token }
}