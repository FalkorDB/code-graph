import { Locator, Page } from "playwright";
import BasePage from "../../infra/ui/basePage";
import { delay, waitToBeEnabled } from "../utils";

declare global {
    interface Window {
        graph: any;
    }
}

export default class CodeGraph extends BasePage {
    /* NavBar Locators*/
    private get falkorDBLogo(): Locator {
        return this.page.locator("//*[img[@alt='FalkorDB']]")
    }

    private get navBaritem(): (navItem: string) => Locator {
        return (navItem: string) => this.page.locator(`//a[p[text() = '${navItem}']]`);
    }

    private get createNewProjectBtn(): Locator {
        return this.page.getByRole('button', { name: 'Create new project' });
    }

    private get createNewProjectDialog(): Locator {
        return this.page.locator("//div[@role='dialog']")
    }

    private get tipBtn(): Locator {
        return this.page.locator("//button[@title='Tip']")
    }

    private get genericMenu(): Locator {
        return this.page.locator("//div[contains(@role, 'menu')]")
    }

    private get tipMenuCloseBtn(): Locator {
        return this.page.locator("//div[@role='menu']//button[@title='Close']")
    }

    /* CodeGraph Locators*/
    private get comboBoxbtn(): Locator {
        return this.page.locator("//button[@role='combobox']")
    }

    private get selectGraphInComboBoxByName(): (graph: string) => Locator {
        return (graph: string) => this.page.locator(`//div[@role='presentation']//div//span[contains(text(), '${graph}')]`);
    }

    private get selectGraphInComboBoxById(): (graph: string) => Locator {
        return (graph: string) => this.page.locator(`//div[@role='presentation']//div[${graph}]`);
    }

    private get lastElementInChat(): Locator {
        return this.page.locator("//main[@data-name='main-chat']/*[last()]/span");
    }

    private get typeUrlInput(): Locator {
        return this.page.locator("//div[@role='dialog']/form/input");
    }

    private get createBtnInCreateProjectDialog(): Locator {
        return this.page.locator("//div[@role='dialog']/form//following::button//p[contains(text(), 'Create')]")
    }

    private get createProjectWaitDialog(): Locator {
        return this.page.locator("//div[@role='dialog']//div//h2[contains(text(), 'THANK YOU FOR A NEW REQUEST')]")
    }

    private get dialogCreatedGraphsList(): (graph: string) => Locator {
        return (graph: string) => this.page.locator(`//div[@role='presentation']/div//span[2][contains(text(), '${graph}')]`);
    }

    private get searchBarInput(): Locator {
        return this.page.locator("//div[@data-name='search-bar']/input");
    }

    private get searchBarAutoCompleteOptions(): Locator {
        return this.page.locator("//div[@data-name='search-bar']/div/button");
    }

    private get searchBarElements(): Locator {
        return this.page.locator("//div[@data-name='search-bar']/div/button/div/p[1]");
    }

    private get searchBarOptionBtn(): (buttonNum: string) => Locator {
        return (buttonNum: string) => this.page.locator(`//div[@data-name='search-bar']//button[${buttonNum}]`);
    }

    private get searchBarList(): Locator {
        return this.page.locator("//div[@data-name='search-bar-list']");
    }

    /* Chat Locators */
    private get showPathBtn(): Locator {
        return this.page.locator("//button[contains(@class, 'Tip')]");
    }

    private get askquestionInput(): Locator {
        return this.page.locator("//input[contains(@placeholder, 'Ask your question')]");
    }

    private get askquestionBtn(): Locator {
        return this.page.locator("//input[contains(@placeholder, 'Ask your question')]/following::button[1]");
    }

    private get lightbulbBtn(): Locator {
        return this.page.locator("//button[@data-name='lightbulb']");
    }

    private get lastChatElementButtonCount(): Locator {
        return this.page.locator("//main[@data-name='main-chat']/*[last()]/button");
    }

    private get chatContainer(): Locator {
        return this.page.locator("//main[@data-name='main-chat']");
    }

    private get previousQuestionLoadingImage(): Locator {
        return this.page.locator("//main[@data-name='main-chat']/*[last()-2]//img[@alt='Waiting for response']")
    }

    private get waitingForResponseImage(): Locator {
        return this.page.locator("//img[@alt='Waiting for response']")
    }

    private get selectInputForShowPath(): (inputNum: string) => Locator {
        return (inputNum: string) => this.page.locator(`(//main[@data-name='main-chat']//input)[${inputNum}]`);
    }

    private get locateNodeInLastChatPath(): (node: string) => Locator {
        return (node: string) => this.page.locator(`(//main[@data-name='main-chat']//span[contains(text(), '${node}')])[last()]`);
    }

    private get selectFirstPathOption(): (inputNum: string) => Locator {
        return (inputNum: string) => this.page.locator(`(//main[@data-name='main-chat']//input)[1]/following::div[${inputNum}]//button[1]`);
    }

    private get notificationError(): Locator {
        return this.page.locator("//div[@role='region']//ol//li");
    }

    private get notificationErrorCloseBtn(): Locator {
        return this.page.locator("//div[@role='region']//ol//li/button");
    }

    private get questionOptionsMenu(): Locator {
        return this.page.locator("//button[@data-name='questionOptionsMenu']");
    }

    private get selectQuestionInMenu(): (questionNumber: string) => Locator {
        return (questionNumber: string) => this.page.locator(`//div[contains(@role, 'menu')]/button[${questionNumber}]`);
    }

    private get lastQuestionInChat(): Locator {
        return this.page.locator("//main[@data-name='main-chat']/*[last()-1]/p");
    }

    /* Canvas Locators*/

    private get canvasElement(): Locator {
        return this.page.locator("//canvas");
    }

    private get zoomInBtn(): Locator {
        return this.page.locator("//button[@title='Zoom In']");
    }

    private get zoomOutBtn(): Locator {
        return this.page.locator("//button[@title='Zoom Out']");
    }

    private get centerBtn(): Locator {
        return this.page.locator("//button[@title='Center']");
    }

    private get codeGraphCheckbox(): (checkbox: string) => Locator {
        return (checkbox: string) => this.page.locator(`(//button[@role='checkbox'])[${checkbox}]`);
    }

    private get clearGraphBtn(): Locator {
        return this.page.locator("//button[p[text()='Reset Graph']]");
    }

    private get unhideNodesBtn(): Locator {
        return this.page.locator("//button[p[text()='Unhide Nodes']]");
    }

    private get elementMenuButton(): (buttonID: string) => Locator {
        return (buttonID: string) => this.page.locator(`//button[@title='${buttonID}']`);
    }

    private get nodeDetailsPanel(): Locator {
        return this.page.locator("//div[@data-name='node-details-panel']");
    }

    private get elementMenu(): Locator {
        return this.page.locator("//div[@id='elementMenu']");
    }
    
    private get nodedetailsPanelHeader(): Locator {
        return this.page.locator("//div[@data-name='node-details-panel']/header/p");
    }
    
    private get nodedetailsPanelcloseBtn(): Locator {
        return this.page.locator("//div[@data-name='node-details-panel']/header/button");
    }
    private get canvasMetricsPanel(): (itemId: string) => Locator {
        return (itemId: string) => this.page.locator(`//div[@data-name='metrics-panel']/p[${itemId}]`);
    }

    private get nodedetailsPanelID(): Locator {
        return this.page.locator("//div[@data-name='node-details-panel']/main/div[1]/p[2]");
    }

    private get nodedetailsPanelElements(): Locator {
        return this.page.locator("//div[@data-name='node-details-panel']/main/div/p[1]");
    }

    private get canvasElementBeforeGraphSelection(): Locator {
        return this.page.locator("//h1[contains(text(), 'Select a repo to show its graph here')]");
    }

    private get copyToClipboardNodePanelDetails(): Locator {
        return this.page.locator(`//div[@data-name='node-details-panel']//button[@title='Copy src to clipboard']`);
    }

    /* NavBar functionality */
    async clickOnFalkorDbLogo(): Promise<Page> {
        await this.page.waitForLoadState('networkidle'); 
        const [newPage] = await Promise.all([
            this.page.waitForEvent('popup'),
            this.falkorDBLogo.click(),
        ]);
        return newPage
    }

    async getNavBarItem(navItem : string): Promise<Page> {
        await this.page.waitForLoadState('networkidle'); 
        const [newPage] = await Promise.all([
            this.page.waitForEvent('popup'),
            this.navBaritem(navItem).click(),
        ]);
        return newPage
    }

    async clickCreateNewProjectBtn(): Promise<void> {
        await this.createNewProjectBtn.click();
    }

    async isCreateNewProjectDialog(): Promise<boolean> {
        return await this.createNewProjectDialog.isVisible();
    }

    async clickonTipBtn(): Promise<void> {
        await this.tipBtn.click();
    }

    async isTipMenuVisible(): Promise<boolean> {
        await delay(500);
        return await this.genericMenu.isVisible();
    }

    async clickonTipMenuCloseBtn(): Promise<void> {
        await this.tipMenuCloseBtn.click();
    }

    /* Chat functionality */
    async clickOnshowPathBtn(): Promise<void> {
        await this.showPathBtn.click();
    }
    
    async clickAskquestionBtn(): Promise<void> {
        await this.askquestionBtn.click();
    }

    async sendMessage(message: string) {
        await waitToBeEnabled(this.askquestionInput);
        await this.askquestionInput.fill(message);
        await this.askquestionBtn.click();
    }

    async clickOnLightBulbBtn(): Promise<void> {
        await this.lightbulbBtn.click();
    }

    async getTextInLastChatElement(): Promise<string>{
        // Wait for loading indicator to disappear
        await this.waitingForResponseImage.waitFor({ state: 'hidden', timeout: 15000 });
        
        // Short delay to ensure text is fully rendered
        await delay(1000);
        
        return (await this.lastElementInChat.textContent())!;
    }

    async getLastChatElementButtonCount(): Promise<number | null>{
        return await this.lastChatElementButtonCount.count();
    }

    async scrollToTop() {
        await this.chatContainer.evaluate((chat) => {
          chat.scrollTop = 0;
        });
    }
    
    async getScrollMetrics() {
        const scrollTop = await this.chatContainer.evaluate((el) => el.scrollTop);
        const scrollHeight = await this.chatContainer.evaluate((el) => el.scrollHeight);
        const clientHeight = await this.chatContainer.evaluate((el) => el.clientHeight);
        return { scrollTop, scrollHeight, clientHeight };
    }

    async isAtBottom(): Promise<boolean> {
        const { scrollTop, scrollHeight, clientHeight } = await this.getScrollMetrics();
        return Math.abs(scrollTop + clientHeight - scrollHeight) < 1;
    }

    async getpreviousQuestionLoadingImage(): Promise<boolean> {
        return this.previousQuestionLoadingImage.isVisible();
    }

    async insertInputForShowPath(inputNum: string, node: string): Promise<void> {
        await this.selectInputForShowPath(inputNum).fill(node);
        await this.selectFirstPathOption(inputNum).click();
    }

    async isNodeVisibleInLastChatPath(node: string): Promise<boolean> {
        await this.locateNodeInLastChatPath(node).waitFor({ state: 'visible' }); 
        return await this.locateNodeInLastChatPath(node).isVisible();
    }

    async isNotificationError(): Promise<boolean> {
        await delay(500);
        return await this.notificationError.isVisible();
    }

    async clickOnNotificationErrorCloseBtn(): Promise<void> {
        await this.notificationErrorCloseBtn.click();
    }

    async clickOnQuestionOptionsMenu(): Promise<void> {
        await this.questionOptionsMenu.click();
    }

    async selectAndGetQuestionInOptionsMenu(questionNumber: string): Promise<string> {
        await this.selectQuestionInMenu(questionNumber).click();
        return await this.selectQuestionInMenu(questionNumber).innerHTML();
    }

    async getLastQuestionInChat(): Promise<string> {
        return await this.lastQuestionInChat.innerText();
    }

    /* CodeGraph functionality */
    async selectGraph(graph: string | number): Promise<void> {
        await this.comboBoxbtn.click();
        if(typeof graph === 'number'){
            await this.selectGraphInComboBoxById(graph.toString()).waitFor({ state : 'visible'})
            await this.selectGraphInComboBoxById(graph.toString()).click();
        } else {
            await this.selectGraphInComboBoxByName(graph).waitFor({ state : 'visible'})
            await this.selectGraphInComboBoxByName(graph).click();
        }
    }

    async createProject(url : string): Promise<void> {
        await this.clickCreateNewProjectBtn();
        await this.typeUrlInput.fill(url);
        await this.createBtnInCreateProjectDialog.click();
        await this.createProjectWaitDialog.waitFor({ state : 'hidden'});
    }

    async isGraphCreated(graph: string): Promise<boolean> {
        await this.comboBoxbtn.click();
        return await this.dialogCreatedGraphsList(graph).isVisible();
    }

    async fillSearchBar(searchValue: string): Promise<void> {
        await this.searchBarInput.fill(searchValue);
    }

    async getSearchAutoCompleteCount(): Promise<number> {
        await this.searchBarAutoCompleteOptions.first().waitFor({ state: 'visible' });
        return await this.searchBarAutoCompleteOptions.count();
    }

    async getSearchBarElementsText(): Promise<string[]> {
        return await this.searchBarElements.allTextContents();
    }

    async selectSearchBarOptionBtn(buttonNum: string): Promise<void> {
        await delay(1000);
        await this.searchBarOptionBtn(buttonNum).click();
    }

    async getSearchBarInputValue(): Promise<string> {
        return await this.searchBarInput.inputValue();
    }
    
    async scrollToBottomInSearchBarList(): Promise<void> {
        await this.searchBarList.evaluate((element) => {
          element.scrollTop = element.scrollHeight;
    })};

    async isScrolledToBottomInSearchBarList(): Promise<boolean> {
        return await this.searchBarList.evaluate((element) => {
          return element.scrollTop + element.clientHeight >= element.scrollHeight;
        });
    }

    /* Canvas functionality */

    async clickZoomIn(): Promise<void> {
        await this.zoomInBtn.click();
    }

    async clickZoomOut(): Promise<void> {
        await this.zoomOutBtn.click();
    }

    async clickCenter(): Promise<void> {
        await this.centerBtn.click();
        await delay(2000); //animation delay
    }

    async clickOnRemoveNodeViaElementMenu(): Promise<void> {
        await this.elementMenuButton("Remove").click();
    }

    async nodeClick(x: number, y: number): Promise<void> {
        await this.waitForCanvasAnimationToEnd();
        for (let attempt = 1; attempt <= 3; attempt++) {
            await this.canvasElement.hover({ position: { x, y } });
            await this.page.waitForTimeout(500);
            await this.canvasElement.click({ position: { x, y }, button: 'left' });
            if (await this.elementMenu.isVisible()) {
                return;
            }
            await this.page.waitForTimeout(1000);
        }
    
        throw new Error(`Failed to click, elementMenu not visible after multiple attempts.`);
    }
    
    async selectCodeGraphCheckbox(checkbox: string): Promise<void> {
        await this.codeGraphCheckbox(checkbox).click();
    }

    async clickOnClearGraphBtn(): Promise<void> {
        await this.clearGraphBtn.click();
    }

    async clickOnUnhideNodesBtn(): Promise<void> {
        await this.unhideNodesBtn.click();
    }

    async changeNodePosition(x: number, y: number): Promise<void> {
        const box = (await this.canvasElement.boundingBox())!;
        const targetX = x + 100;
        const targetY = y + 50;
        const absStartX = box.x + x;
        const absStartY = box.y + y;
        const absEndX = box.x + targetX;
        const absEndY = box.y + targetY;
        await this.page.mouse.move(absStartX, absStartY);
        await this.page.mouse.down();
        await this.page.mouse.move(absEndX, absEndY);
        await this.page.mouse.up();
    }

    async isNodeDetailsPanel(): Promise<boolean> {
        return this.nodeDetailsPanel.isVisible();
    }

    async clickOnViewNode(): Promise<void> {
        await this.elementMenuButton("View Node").click();
    }

    async getNodeDetailsHeader(): Promise<string> {
        await this.elementMenuButton("View Node").click();
        const text = await this.nodedetailsPanelHeader.innerHTML();
        return text;
    }

    async clickOnNodeDetailsCloseBtn(): Promise<void>{
        await this.nodedetailsPanelcloseBtn.click();
    }

    async getMetricsPanelInfo(): Promise<{nodes: string, edges: string}> {
        const nodes = await this.canvasMetricsPanel("1").innerHTML();
        const edges = await this.canvasMetricsPanel("2").innerHTML();
        return { nodes, edges }
    }

    async clickOnCopyToClipboardNodePanelDetails(): Promise<string> {
        await this.copyToClipboardNodePanelDetails.click();
        await delay(1000)
        return await this.page.evaluate(() => navigator.clipboard.readText());
    }

    async clickOnCopyToClipboard(): Promise<string> {
        await this.elementMenuButton("Copy src to clipboard").click();
        await delay(1000)
        return await this.page.evaluate(() => navigator.clipboard.readText());
    }

    async getNodedetailsPanelID(): Promise<string> {
        return await this.nodedetailsPanelID.innerHTML();
    }

    async getNodeDetailsPanelElements(): Promise<string[]> {
        await this.elementMenuButton("View Node").click();
        await delay(500)
        const elements = await this.nodedetailsPanelElements.all();
        return Promise.all(elements.map(element => element.innerHTML()));
    }

    async getGraphNodes(): Promise<any[]> {
        await this.waitForCanvasAnimationToEnd();
    
        const graphData = await this.page.evaluate(() => {
            return (window as any).graph;
        });
    
        let transformData: any = null;
        for (let attempt = 0; attempt < 3; attempt++) {
            await this.page.waitForTimeout(1000);
    
            transformData = await this.canvasElement.evaluate((canvas: HTMLCanvasElement) => {
                const rect = canvas.getBoundingClientRect();
                const ctx = canvas.getContext('2d');
                return {
                    left: rect.left,
                    top: rect.top,
                    transform: ctx?.getTransform() || null,
                };
            });
    
            if (transformData.transform) break;
            console.warn(`Attempt ${attempt + 1}: Transform data not available, retrying...`);
        }
    
        if (!transformData?.transform) throw new Error("Canvas transform data not available!");
    
        const { a, e, d, f } = transformData.transform;
        return graphData.elements.nodes.map((node: any) => ({
            ...node,
            screenX: transformData.left + node.x * a + e - 35,
            screenY: transformData.top + node.y * d + f - 190,
        }));
    }
   
    async getCanvasScaling(): Promise<{ scaleX: number; scaleY: number }> {
        const { scaleX, scaleY } = await this.canvasElement.evaluate((canvas: HTMLCanvasElement) => {
            const ctx = canvas.getContext('2d');
            const transform = ctx?.getTransform();
            return {
                scaleX: transform?.a || 1,
                scaleY: transform?.d || 1,
            };
        });
        return { scaleX, scaleY };
    }

    async getGraphDetails(): Promise<any> {
        await this.canvasElementBeforeGraphSelection.waitFor({ state: 'detached' });
        await this.waitForCanvasAnimationToEnd();
        await this.page.waitForFunction(() => !!window.graph);
    
        const graphData = await this.page.evaluate(() => {
            return window.graph;
        });
        
        return graphData;
    }

    async waitForCanvasAnimationToEnd(timeout = 15000, checkInterval = 500): Promise<void> {
        const canvasHandle = await this.canvasElement.elementHandle();
    
        if (!canvasHandle) {
            throw new Error("Canvas element not found!");
        }
    
        await this.page.waitForFunction(
            async ({ canvas, checkInterval, timeout }) => {
                const ctx = canvas.getContext('2d');
                if (!ctx) return false;
    
                const width = canvas.width;
                const height = canvas.height;
    
                let previousData = ctx.getImageData(0, 0, width, height).data;
                const startTime = Date.now();
    
                return new Promise<boolean>((resolve) => {
                    const checkCanvas = () => {
                        if (Date.now() - startTime > timeout) {
                            resolve(true);
                            return;
                        }
    
                        setTimeout(() => {
                            const currentData = ctx.getImageData(0, 0, width, height).data;
                            if (JSON.stringify(previousData) === JSON.stringify(currentData)) {
                                resolve(true);
                            } else {
                                previousData = currentData;
                                checkCanvas();
                            }
                        }, checkInterval);
                    };
                    checkCanvas();
                });
            },
            { 
                canvas: await canvasHandle.evaluateHandle((el) => el as HTMLCanvasElement),
                checkInterval,
                timeout
            },
            { timeout }
        );
    }

}
