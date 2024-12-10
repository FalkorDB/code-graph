import { Locator } from "@playwright/test";

export type Pixel = { x: number; y: number };

export interface CanvasAnalysisResult {
    red: Array<{ x: number; y: number; radius: number }>;
    yellow: Array<{ x: number; y: number; radius: number }>;
    green: Array<{ x: number; y: number; radius: number }>;
}

export async function analyzeCanvasNodes(locator: Locator): Promise<CanvasAnalysisResult> {
    const canvasHandle = await locator.evaluateHandle((canvas) => canvas as HTMLCanvasElement);
    const canvasElement = await canvasHandle.asElement();
    if (!canvasElement) {
        throw new Error("Failed to retrieve canvas element");
    }

    // Retrieve the original canvas width
    const originalCanvasWidth = await canvasElement.evaluate((canvas) => canvas.width);

    const result = await canvasElement.evaluate(
        (canvas, originalWidth) => {
            const ctx = canvas?.getContext("2d");
            if (!ctx) {
                throw new Error("Failed to get 2D context");
            }

            const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const { data, width, height } = imageData;

            const scaleFactor = canvas.width / originalWidth;
            const adjustedRadius = 3 / scaleFactor;
            const adjustedMergeRadius = 10 / scaleFactor;

            type Pixel = { x: number; y: number };

            const redPixels: Pixel[] = [];
            const yellowPixels: Pixel[] = [];
            const greenPixels: Pixel[] = [];

            const isRedPixel = (r: number, g: number, b: number) => r > 170 && g < 120 && b < 120;
            const isYellowPixel = (r: number, g: number, b: number) => r > 170 && g > 170 && b < 130;
            const isGreenPixel = (r: number, g: number, b: number) => g > 120 && g > r && g > b && r < 50 && b < 160;

            for (let y = 0; y < height; y++) {
                for (let x = 0; x < width; x++) {
                    const i = (y * width + x) * 4;
                    const r = data[i];
                    const g = data[i + 1];
                    const b = data[i + 2];

                    if (isRedPixel(r, g, b)) redPixels.push({ x, y });
                    if (isYellowPixel(r, g, b)) yellowPixels.push({ x, y });
                    if (isGreenPixel(r, g, b)) greenPixels.push({ x, y });
                }
            }

            const clusterNodes = (pixels: Pixel[], radius: number): Pixel[][] => {
                const visited = new Set<string>();
                const clusters: Pixel[][] = [];
            
                pixels.forEach((pixel) => {
                    const key = `${pixel.x},${pixel.y}`;
                    if (visited.has(key)) return;
            
                    const cluster: Pixel[] = [];
                    const stack: Pixel[] = [pixel];
            
                    while (stack.length > 0) {
                        const current = stack.pop()!;
                        const currentKey = `${current.x},${current.y}`;
                        if (visited.has(currentKey)) continue;
            
                        visited.add(currentKey);
                        cluster.push(current);
            
                        pixels.forEach((neighbor) => {
                            const dist = Math.sqrt(
                                (current.x - neighbor.x) ** 2 + (current.y - neighbor.y) ** 2
                            );
                            if (dist <= radius && !visited.has(`${neighbor.x},${neighbor.y}`)) {
                                stack.push(neighbor);
                            }
                        });
                    }
            
                    clusters.push(cluster);
                });
            
                return clusters;
            };
            
            

            const mergeCloseClusters = (clusters: Pixel[][], mergeRadius: number): Pixel[][] => {
                const mergedClusters: Pixel[][] = [];
                const usedClusters = new Set<number>();
            
                for (let i = 0; i < clusters.length; i++) {
                    if (usedClusters.has(i)) continue;
            
                    let merged = [...clusters[i]];
            
                    for (let j = i + 1; j < clusters.length; j++) {
                        if (usedClusters.has(j)) continue;
            
                        const dist = Math.sqrt(
                            (merged[0].x - clusters[j][0].x) ** 2 +
                            (merged[0].y - clusters[j][0].y) ** 2
                        );
            
                        if (dist <= mergeRadius) {
                            merged = [...new Set([...merged, ...clusters[j]])]; // Deduplicate pixels
                            usedClusters.add(j);
                        }
                    }
            
                    mergedClusters.push(merged);
                    usedClusters.add(i);
                }
            
                return mergedClusters;
            };
            

            const redClusters = clusterNodes(redPixels, adjustedRadius);
            const yellowClusters = clusterNodes(yellowPixels, adjustedRadius);
            const greenClusters = clusterNodes(greenPixels, adjustedRadius);

            const mergedGreenClusters = mergeCloseClusters(greenClusters, adjustedMergeRadius);

            const filteredRedClusters = redClusters.filter((cluster) => cluster.length >= 5);
            const filteredYellowClusters = yellowClusters.filter((cluster) => cluster.length >= 5);
            const filteredGreenClusters = mergedGreenClusters.filter((cluster) => cluster.length >= 5);

            const calculateRadius = (cluster: Pixel[], scaleFactor: number) => {
                const rawRadius = Math.sqrt(cluster.length / Math.PI) / scaleFactor;
                return Math.round(rawRadius * 1000) / 1000;
            };

            return {
                red: filteredRedClusters.map(cluster => ({
                    x: cluster.reduce((sum, p) => sum + p.x, 0) / cluster.length,
                    y: cluster.reduce((sum, p) => sum + p.y, 0) / cluster.length,
                    radius: calculateRadius(cluster, scaleFactor)
                })),
                yellow: filteredYellowClusters.map(cluster => ({
                    x: cluster.reduce((sum, p) => sum + p.x, 0) / cluster.length,
                    y: cluster.reduce((sum, p) => sum + p.y, 0) / cluster.length,
                    radius: calculateRadius(cluster, scaleFactor)
                })),
                green: filteredGreenClusters.map(cluster => ({
                    x: cluster.reduce((sum, p) => sum + p.x, 0) / cluster.length,
                    y: cluster.reduce((sum, p) => sum + p.y, 0) / cluster.length,
                    radius: calculateRadius(cluster, scaleFactor)
                }))
            };
        },
        originalCanvasWidth
    );

    await canvasHandle.dispose();
    return result;
}
