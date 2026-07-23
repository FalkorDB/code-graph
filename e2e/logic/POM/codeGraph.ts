import { Download, Locator } from "@playwright/test";
import BasePage from "../../infra/ui/basePage";
import { interactWhenVisible, waitForElementToBeVisible, waitForStableText, waitToBeEnabled } from "../utils";

declare global {
    interface Window {
        graph: any;
    }
}

export default class CodeGraph extends BasePage {

    private isMobile: boolean = false;

    public setMobileState(isMobile: boolean): void {
        this.isMobile = isMobile;
    }

    private get container(): Locator {
        return this.page.locator(this.isMobile ? "#mobile" : "#desktop");
    }

    private get scopedLocator(): (selector: string) => Locator {
        return (selector: string) => this.container.locator(selector);
    }

    private get activeGraphGetterName(): "graphDesktop" | "graphMobile" {
        return this.isMobile ? "graphMobile" : "graphDesktop";
    }

    /* NavBar Locators*/
    private get falkorDBLogo(): Locator {
        return this.scopedLocator("//a[@aria-label='FalkorDB']")
    }

    private get navBaritem(): (navItem: string) => Locator {
        return (navItem: string) => {
            const navItemSelectors: Record<string, string> = {
                "Main Website": "//a[@title='Home' or .//p[normalize-space()='Main Website'] or contains(@href, 'falkordb.com')]",
                "GitHub": "//a[@title='GitHub' or .//p[normalize-space()='GitHub'] or contains(@href, 'github.com/FalkorDB/code-graph')]",
                "Discord": "//a[@title='Discord' or .//p[normalize-space()='Discord'] or contains(@href, 'discord.gg/falkordb')]",
            };
            const selector = navItemSelectors[navItem] ?? `//a[@title='${navItem}' or .//p[normalize-space()='${navItem}']]`;
            return this.scopedLocator(selector).first();
        };
    }

    private get createNewProjectBtn(): Locator {
        return this.page.getByRole('button', { name: 'Create new project' });
    }

    private get createNewProjectDialog(): Locator {
        return this.scopedLocator("//div[@role='dialog']")
    }

    private get tipBtn(): Locator {
        return this.scopedLocator("//button[@title='Tip']")
    }

    private get genericMenu(): Locator {
        return this.page.locator("//div[contains(@role, 'menu')]")
    }

    private get tipMenuCloseBtn(): Locator {
        return this.page.locator("//div[@role='menu']//button[@title='Close']")
    }

    /* CodeGraph Locators*/
    private get comboBoxbtn(): Locator {
        return this.scopedLocator("//button[@role='combobox']")
    }

    private get selectGraphInComboBoxByName(): (graph: string) => Locator {
        return (graph: string) => this.page.locator(`//div[@role='presentation']//div//span[contains(text(), '${graph}')]`).first();
    }

    private get selectGraphInComboBoxById(): (graph: string) => Locator {
        return (graph: string) => this.page.locator(`//div[@role='presentation']//div[${graph}]`);
    }

    private get lastElementInChat(): Locator {
        return this.scopedLocator("//main[@data-name='main-chat']/*[last()]/span");
    }

    private get typeUrlInput(): Locator {
        return this.scopedLocator("//div[@role='dialog']/form/input");
    }

    private get createBtnInCreateProjectDialog(): Locator {
        return this.scopedLocator("//div[@role='dialog']/form//following::button//p[contains(text(), 'Create')]")
    }

    private get createProjectWaitDialog(): Locator {
        return this.scopedLocator("//div[@role='dialog']//div//h2[contains(text(), 'THANK YOU FOR A NEW REQUEST')]")
    }

    private get dialogCreatedGraphsList(): (graph: string) => Locator {
        return (graph: string) => this.scopedLocator(`//div[@role='presentation']/div//span[2][contains(text(), '${graph}')]`);
    }

    private get searchBarInput(): Locator {
        return this.scopedLocator("//div[@data-name='search-bar']/input");
    }

    private get searchBarAutoCompleteOptions(): Locator {
        return this.scopedLocator("//div[@data-name='search-bar']/div/button");
    }

    private get searchBarElements(): Locator {
        return this.scopedLocator("//div[@data-name='search-bar']/div/button/div/p[1]");
    }

    private get searchBarOptionBtn(): (buttonNum: string) => Locator {
        return (buttonNum: string) => this.scopedLocator(`//div[@data-name='search-bar']//button[${buttonNum}]`);
    }

    private get searchBarList(): Locator {
        return this.scopedLocator('div[data-name="search-bar-list"]');
    }

    private get searchBarListFirstButtonInput(): Locator {
        return this.searchBarList.locator("button").first().locator('div p').first();
    }

    /* Chat Locators */

    private get showPathBtn(): (selection: string) => Locator {
        return (selection: string) => this.page.locator(`//button[contains(@class, 'Tip')]//p[contains(text(), '${selection}')]`);
    }

    private get askquestionInput(): Locator {
        return this.scopedLocator("//input[contains(@placeholder, 'Ask your question')]");
    }

    private get askquestionBtn(): Locator {
        return this.scopedLocator("//input[contains(@placeholder, 'Ask your question')]/following::button[1]");
    }

    private get lightbulbBtn(): Locator {
        return this.scopedLocator("//button[@data-name='lightbulb']");
    }

    private get lastChatElementButtonCount(): Locator {
        return this.scopedLocator("//main[@data-name='main-chat']/*[last()]/button");
    }

    private get chatContainer(): Locator {
        return this.scopedLocator("//main[@data-name='main-chat']");
    }

    private get previousQuestionLoadingImage(): Locator {
        return this.scopedLocator("//main[@data-name='main-chat']/*[last()-2]//img[@alt='Waiting for response']")
    }

    private get waitingForResponseImage(): Locator {
        return this.page.locator("//img[@alt='Waiting for response']")
    }

    private get selectInputForShowPath(): (inputNum: string) => Locator {
        return (inputNum: string) => this.scopedLocator(`(//main[@data-name='main-chat']//input)[${inputNum}]`);
    }

    private get locateNodeInLastChatPath(): (node: string) => Locator {
        return (node: string) => this.page.locator(`(//main[@data-name='main-chat']//button//span[contains(text(), '${node}')])[last()]`);
    }

    private get selectFirstPathOption(): (inputNum: string) => Locator {
        return (inputNum: string) => this.scopedLocator(`(//main[@data-name='main-chat']//input)[1]/following::div[${inputNum}]//button[1]`);
    }

    private get notificationError(): Locator {
        return this.page.locator("//div[@role='region']//ol//li");
    }

    private get notificationErrorCloseBtn(): Locator {
        return this.page.locator("//div[@role='region']//ol//li/button");
    }

    private get selectQuestionInMenu(): (questionNumber: string) => Locator {
        return (questionNumber: string) => this.page.locator(`//div[contains(@role, 'menu')]/button[${questionNumber}]`);
    }

    private get lastQuestionInChat(): Locator {
        return this.scopedLocator("//main[@data-name='main-chat']/*[last()-1]/p");
    }

    private get responseLoadingImg(): Locator {
        return this.scopedLocator("//img[@alt='Waiting for response']");
    }

    private get waitingForResponseIndicator(): Locator {
        return this.scopedLocator('img[alt="Waiting for response"]');
    }

    /* Canvas Locators*/

    private get canvasElement(): Locator {
        return this.scopedLocator("//falkordb-canvas").locator("canvas").first();
    }

    private get canvasHost(): Locator {
        return this.scopedLocator("falkordb-canvas").first();
    }

    private get zoomInBtn(): Locator {
        return this.scopedLocator("//button[@title='Zoom In']");
    }

    private get zoomOutBtn(): Locator {
        return this.scopedLocator("//button[@title='Zoom Out']");
    }

    private get centerBtn(): Locator {
        return this.scopedLocator("//button[@title='Center']");
    }

    private get codeGraphCheckbox(): (checkbox: string) => Locator {
        return (checkbox: string) => this.scopedLocator(`(//button[@role='checkbox'])[${checkbox}]`);
    }

    private get categoryCheckbox(): (category: string) => Locator {
        return (category: string) => this.scopedLocator(`//p[text()='${category}']/preceding-sibling::button[@role='checkbox']`);
    }

    private get clearGraphBtn(): Locator {
        return this.container.getByRole('button', { name: 'Reset Graph' });
    }

    private get unhideNodesBtn(): Locator {
        return this.container.getByRole('button', { name: 'Unhide Nodes' });
    }

    private get elementMenuButton(): (buttonID: string) => Locator {
        return (buttonID: string) => this.page.locator(`//button[@title='${buttonID}']`);
    }

    private get nodeDetailsPanel(): Locator {
        return this.scopedLocator("//div[@data-name='node-details-panel']");
    }

    private get elementMenu(): Locator {
        return this.page.locator("//div[@id='elementMenu']");
    }

    private get nodedetailsPanelHeader(): Locator {
        return this.scopedLocator("//div[@data-name='node-details-panel']/header/p");
    }

    private get nodedetailsPanelcloseBtn(): Locator {
        return this.scopedLocator("//div[@data-name='node-details-panel']/header/button");
    }
    private get canvasMetricsPanel(): (itemId: string) => Locator {
        return (itemId: string) => this.scopedLocator(`//div[@data-name='metrics-panel']/p[${itemId}]`);
    }

    private get nodedetailsPanelID(): Locator {
        return this.scopedLocator("//div[@data-name='node-details-panel']/main/div[1]/p[2]");
    }

    private get nodedetailsPanelElements(): Locator {
        return this.scopedLocator("//div[@data-name='node-details-panel']/main/div/p[1]");
    }

    private get canvasElementBeforeGraphSelection(): Locator {
        return this.scopedLocator("//h1[contains(text(), 'Select a repo to show its graph here')]");
    }

    private get copyToClipboardNodePanelDetails(): Locator {
        return this.scopedLocator(`//div[@data-name='node-details-panel']//button[@title='Copy src to clipboard']`);
    }

    private get canvasTooltip(): Locator {
        return this.page.locator('.float-tooltip-kap').first();
    }

    private get nodeToolTip(): (node: string) => Locator {
        return (node: string) => this.page.locator('.float-tooltip-kap').filter({ hasText: node });
    }

    private get downloadImageBtn(): Locator {
        return this.scopedLocator("//button[@title='downloadImage']");
    }

    /* NavBar functionality */
    async clickOnFalkorDbLogo(): Promise<string | null> {
        await this.page.waitForLoadState('networkidle');
        await interactWhenVisible(this.falkorDBLogo, async () => {}, 'FalkorDB Logo');
        return this.falkorDBLogo.getAttribute('href');
    }

    async getNavBarItem(navItem: string): Promise<string | null> {
        await this.page.waitForLoadState('networkidle');
        await interactWhenVisible(this.navBaritem(navItem), async () => {}, `NavBar item: ${navItem}`);
        return this.navBaritem(navItem).getAttribute('href');
    }

    async clickCreateNewProjectBtn(): Promise<void> {
        await interactWhenVisible(this.createNewProjectBtn, (el) => el.click(), 'Create New Project button');
    }

    async isCreateNewProjectDialog(): Promise<boolean> {
        return await waitForElementToBeVisible(this.createNewProjectDialog);
    }

    async clickOnTipBtn(): Promise<void> {
        await interactWhenVisible(this.tipBtn, (el) => el.click(), 'Tip button');
    }

    async isTipMenuVisible(): Promise<boolean> {
        await this.page.waitForTimeout(500);
        return await this.genericMenu.isVisible();
    }

    async clickOnTipMenuCloseBtn(): Promise<void> {
        await interactWhenVisible(this.tipMenuCloseBtn, (el) => el.click(), 'Tip Menu Close button');
    }


    /* Chat functionality */
    async clickOnShowPathBtn(selection: string): Promise<void> {
        await interactWhenVisible(this.showPathBtn(selection), (el) => el.click(), `Show Path button: ${selection}`);
    }

    async clickAskQuestionBtn(): Promise<void> {
        await interactWhenVisible(this.askquestionBtn, (el) => el.click(), 'Ask Question button');
    }

    async sendMessage(message: string) {
        await waitToBeEnabled(this.askquestionBtn);
        await interactWhenVisible(this.askquestionInput, (el) => el.fill(message), 'Ask question input');
        await interactWhenVisible(this.askquestionBtn, (el) => el.click(), 'Ask Question button');
    }

    async clickOnLightBulbBtn(): Promise<void> {
        await interactWhenVisible(this.lightbulbBtn, (el) => el.click(), 'Light Bulb button');
    }

    async getTextInLastChatElement(): Promise<string> {
        await this.waitingForResponseIndicator.waitFor({ state: 'hidden' });
        await this.page.waitForTimeout(2000);
        return await waitForStableText(this.lastElementInChat, 10000);
    }

    async getLastChatElementButtonCount(): Promise<number | null> {
        return await this.lastChatElementButtonCount.count();
    }

    async scrollToTop(): Promise<void> {
        const isVisible = await waitForElementToBeVisible(this.chatContainer);
        if (!isVisible) throw new Error("Chat container is not visible!");

        await this.chatContainer.evaluate((chat) => {
            chat.scrollTop = 0;
        });
    }

    async getScrollMetrics() {
        const isVisible = await waitForElementToBeVisible(this.chatContainer);
        if (!isVisible) throw new Error("Chat container is not visible!");

        return await this.chatContainer.evaluate((el) => ({
            scrollTop: el.scrollTop,
            scrollHeight: el.scrollHeight,
            clientHeight: el.clientHeight
        }));
    }

    async isAtBottom(): Promise<boolean> {
        const { scrollTop, scrollHeight, clientHeight } = await this.getScrollMetrics();
        return Math.abs(scrollTop + clientHeight - scrollHeight) < 1;
    }

    async getpreviousQuestionLoadingImage(): Promise<boolean> {
        return this.previousQuestionLoadingImage.isVisible();
    }

    async insertInputForShowPath(inputNum: string, node: string): Promise<void> {
        await interactWhenVisible(this.selectInputForShowPath(inputNum), (el) => el.fill(node), `Path input ${inputNum}`);
        await interactWhenVisible(this.selectFirstPathOption(inputNum), (el) => el.click(), `Path option ${inputNum}`);
    }

    async fillPathInputsAndWait(firstNode: string, secondNode: string): Promise<void> {
        await this.insertInputForShowPath("1", firstNode);
        const pathResponsePromise = this.page.waitForResponse(
            resp => resp.url().includes('/api/find_paths'),
            { timeout: 15000 }
        );
        await this.insertInputForShowPath("2", secondNode);
        await pathResponsePromise;
        await this.page.waitForTimeout(2000);
    }

    async isNodeVisibleInLastChatPath(node: string): Promise<boolean> {
        // Wait for PathResponse buttons to render in the chat
        await this.page.waitForSelector(
            `main[data-name='main-chat'] button span`,
            { state: 'visible', timeout: 10000 }
        ).catch(() => {});
        await this.page.mouse.click(10, 10);
        const nodeLocator = this.locateNodeInLastChatPath(node);
        return await waitForElementToBeVisible(nodeLocator, 1000, 10);
    }

    async isNotificationError(): Promise<boolean> {
        await this.page.waitForTimeout(500);
        return await this.notificationError.isVisible();
    }

    async clickOnNotificationErrorCloseBtn(): Promise<void> {
        await interactWhenVisible(this.notificationErrorCloseBtn, (el) => el.click(), 'Notification Error Close button');
    }

    async selectAndGetQuestionInOptionsMenu(questionNumber: string): Promise<string> {
        const question = this.selectQuestionInMenu(questionNumber);
        const text = await question.innerText();
        await interactWhenVisible(question, (el) => el.click(), `Question option ${questionNumber}`);
        return text;
    }

    async getLastQuestionInChat(): Promise<string> {
        const isVisible = await waitForElementToBeVisible(this.lastQuestionInChat);
        if (!isVisible) throw new Error("Last question in chat is not visible!");
        return (await this.lastQuestionInChat.innerText()) ?? "";
    }

    /* CodeGraph functionality */
    async selectGraph(graph: string | number): Promise<void> {
        const previousGraphSnapshot = await this.getActiveGraphSnapshot();
        await interactWhenVisible(this.comboBoxbtn, (el) => el.click(), 'ComboBox button');
        if (typeof graph === 'number') {
            await interactWhenVisible(this.selectGraphInComboBoxById(graph.toString()), (el) => el.click(), `Graph option ${graph}`);
        } else {
            await interactWhenVisible(this.selectGraphInComboBoxByName(graph), (el) => el.click(), `Graph option ${graph}`);
        }
        await this.page.waitForFunction(({ getterName, previousGraphId, previousNodeIds }) => {
            const getter = (window as any)[getterName];
            const graphData = typeof getter === "function" ? getter() : null;
            const nodes = graphData?.elements?.nodes || graphData?.nodes;
            if (!Array.isArray(nodes) || nodes.length === 0) return false;

            const currentGraphId = (window as any).graph?.Id != null ? String((window as any).graph.Id) : null;
            if (currentGraphId !== previousGraphId) return true;

            const currentNodeIds = nodes.map((node: { id: string | number }) => String(node.id)).sort();
            if (currentNodeIds.length !== previousNodeIds.length) return true;

            return currentNodeIds.some((id: string, index: number) => id !== previousNodeIds[index]);
        }, {
            getterName: this.activeGraphGetterName,
            previousGraphId: previousGraphSnapshot.graphId,
            previousNodeIds: previousGraphSnapshot.nodeIds,
        }, { timeout: 10000 });
        await this.waitForCanvasViewportToSettle();
    }

    async createProject(url: string): Promise<void> {
        await this.clickCreateNewProjectBtn();
        await interactWhenVisible(this.typeUrlInput, (el) => el.fill(url), 'URL input');
        await interactWhenVisible(this.createBtnInCreateProjectDialog, (el) => el.click(), 'Create button');
        await this.createProjectWaitDialog.waitFor({ state: 'hidden' });
    }

    async isGraphCreated(graph: string): Promise<boolean> {
        await interactWhenVisible(this.comboBoxbtn, (el) => el.click(), 'ComboBox button');
        return await this.dialogCreatedGraphsList(graph).isVisible();
    }

    async fillSearchBar(searchValue: string): Promise<void> {
        await interactWhenVisible(this.searchBarInput, (el) => el.fill(searchValue), 'Search bar input');
    }

    async getSearchAutoCompleteCount(): Promise<number> {
        await interactWhenVisible(this.searchBarAutoCompleteOptions.first(), async () => {}, 'Search auto-complete options');
        return await this.searchBarAutoCompleteOptions.count();
    }

    async getSearchBarElementsText(): Promise<string[]> {
        return await this.searchBarElements.allTextContents();
    }

    async selectSearchBarOptionBtn(buttonNum: string): Promise<void> {
        await interactWhenVisible(this.searchBarOptionBtn(buttonNum), (el) => el.click(), `Search bar option ${buttonNum}`);
    }

    async getSearchBarInputValue(): Promise<string | null> {
        const isVisible = await waitForElementToBeVisible(this.searchBarListFirstButtonInput);
        if (!isVisible) return null;
        return (await this.searchBarListFirstButtonInput.innerText())?.trim() ?? null;
    }

    async scrollToBottomInSearchBarList(): Promise<void> {
        await this.searchBarList.evaluate((element) => {
            element.scrollTop = element.scrollHeight;
        })
    };

    async isScrolledToBottomInSearchBarList(): Promise<boolean> {
        return await this.searchBarList.evaluate((element) => {
            return element.scrollTop + element.clientHeight >= element.scrollHeight;
        });
    }

    /* Canvas functionality */

    async clickZoomIn(): Promise<void> {
        await interactWhenVisible(this.zoomInBtn, (el) => el.click(), 'Zoom In button');
        await this.waitForCanvasAnimationToEnd();
    }

    async clickZoomOut(): Promise<void> {
        await interactWhenVisible(this.zoomOutBtn, (el) => el.click(), 'Zoom Out button');
        await this.waitForCanvasAnimationToEnd();
    }

    async clickCenter(): Promise<void> {
        await interactWhenVisible(this.centerBtn, (el) => el.click(), 'Center button');
        await this.waitForCanvasAnimationToEnd();
    }

    async clickOnRemoveNodeViaElementMenu(): Promise<void> {
        await interactWhenVisible(
            this.elementMenuButton("Remove"), (el) => el.click(), 'Remove button'
        );
    }

    async nodeClick(x: number, y: number): Promise<void> {
        await this.waitForCanvasAnimationToEnd();
        const boundingBox = await this.canvasElement.boundingBox();
        if (!boundingBox) throw new Error("Canvas bounding box not found");
        const maxX = boundingBox.x + boundingBox.width;
        const maxY = boundingBox.y + boundingBox.height;
        if (x < boundingBox.x || x > maxX || y < boundingBox.y || y > maxY) {
            throw new Error(
                `Node click coordinates (${x}, ${y}) are outside canvas bounds ` +
                `[${boundingBox.x}, ${maxX}] x [${boundingBox.y}, ${maxY}]`
            );
        }

        for (let attempt = 1; attempt <= 3; attempt++) {
            await this.page.mouse.move(x, y);
            await this.page.waitForTimeout(500);
            await this.page.mouse.click(x, y, { button: 'right' });
            if (await waitForElementToBeVisible(this.elementMenuButton("View Node"), 100, 5)) {
                return;
            }
            await this.page.waitForTimeout(1000);
        }

        throw new Error(`Failed to open node context menu at (${x}, ${y}); "View Node" did not appear after multiple attempts.`);
    }


    async selectCodeGraphCheckbox(checkbox: string): Promise<void> {
        await interactWhenVisible(this.codeGraphCheckbox(checkbox), (el) => el.click(), `Checkbox ${checkbox}`);
    }

    async selectCategoryCheckbox(category: string): Promise<void> {
        await interactWhenVisible(this.categoryCheckbox(category), (el) => el.click(), `Category checkbox ${category}`);
    }

    async clickOnClearGraphBtn(): Promise<void> {
        await this.page.mouse.click(10, 10);
        await interactWhenVisible(this.clearGraphBtn, (el) => el.click(), 'Clear Graph button');
    }

    async clickOnUnhideNodesBtn(): Promise<void> {
        await interactWhenVisible(
            this.unhideNodesBtn, (el) => el.click(), `Unhide Nodes Button`
        );
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

    async dragFromCanvasCenter(): Promise<void> {
        const box = (await this.canvasElement.boundingBox())!;
        const centerX = box.x + box.width / 2;
        const centerY = box.y + box.height / 2;
        await this.page.mouse.move(centerX, centerY);
        await this.page.mouse.down();
        await this.page.mouse.move(centerX + 100, centerY + 50);
        await this.page.mouse.up();
    }

    async isNodeDetailsPanel(): Promise<boolean> {
        await this.page.waitForTimeout(500);
        return this.nodeDetailsPanel.isVisible();
    }

    async clickOnViewNode(): Promise<void> {
        await interactWhenVisible(
            this.elementMenuButton("View Node"), (el) => el.click(), 'View Node button'
        );
    }

    async getNodeDetailsHeader(): Promise<string> {
        const isMenuVisible = await waitForElementToBeVisible(this.elementMenu);
        if (!isMenuVisible) throw new Error("Element menu did not appear!");

        await this.clickOnViewNode();

        const isHeaderVisible = await waitForElementToBeVisible(this.nodedetailsPanelHeader);
        if (!isHeaderVisible) throw new Error("Node details panel header did not appear!");

        return this.nodedetailsPanelHeader.innerHTML();
    }

    async clickOnNodeDetailsCloseBtn(): Promise<void> {
        await interactWhenVisible(this.nodedetailsPanelcloseBtn, (el) => el.click(), 'Node Details Close button');
    }

    async getMetricsPanelInfo(): Promise<{ nodes: string, edges: string }> {
        // The metrics panel is populated by an async /api/repo_info fetch
        // that fires after graph selection resolves, so it can briefly read
        // "0" right after selectGraph(). Poll until it settles on a
        // non-zero value (or give up and return whatever is last read).
        let nodes = "0";
        let edges = "0";
        for (let attempt = 0; attempt < 10; attempt++) {
            nodes = await this.canvasMetricsPanel("1").innerHTML();
            edges = await this.canvasMetricsPanel("3").innerHTML();
            // innerHTML is e.g. "495 Nodes" / "806 Edges" — parse the number
            if (parseInt(nodes, 10) > 0 || parseInt(edges, 10) > 0) break;
            await this.page.waitForTimeout(500);
        }
        return { nodes, edges }
    }

    async clickOnCopyToClipboardNodePanelDetails(): Promise<string> {
        await interactWhenVisible(this.copyToClipboardNodePanelDetails, (el) => el.click(), 'Copy to clipboard button');
        return await this.page.evaluate(() => navigator.clipboard.readText());
    }

    async clickOnCopyToClipboard(): Promise<string> {
        await interactWhenVisible(
            this.elementMenuButton("Copy src to clipboard"), (el) => el.click(), 'Copy src to clipboard button'
        );
        return await this.page.evaluate(() => navigator.clipboard.readText());
    }

    async getNodedetailsPanelID(): Promise<string> {
        return await this.nodedetailsPanelID.innerHTML();
    }

    async getNodeDetailsPanelElements(): Promise<string[]> {
        await interactWhenVisible(
            this.elementMenuButton("View Node"), (el) => el.click(), 'View Node button'
        );
        await interactWhenVisible(
            this.nodedetailsPanelElements.first(), async () => {}, 'Node details panel'
        );
        const elements = await this.nodedetailsPanelElements.all();
        return Promise.all(elements.map(element => element.innerHTML()));
    }

    private async waitForGraphData(): Promise<any> {
        await this.waitForCanvasAnimationToEnd();
        await this.page.waitForFunction((getterName) => {
            const getter = (window as any)[getterName];
            const data = typeof getter === "function" ? getter() : null;
            const nodes = data?.elements?.nodes || data?.nodes;
            return Array.isArray(nodes) && nodes.length > 0;
        }, this.activeGraphGetterName, { timeout: 5000 });
        await this.page.waitForTimeout(3000);
        await this.waitForCanvasAnimationToEnd();

        const graphData = await this.getActiveGraphData();
        if (!graphData) throw new Error(`Graph data not available from ${this.activeGraphGetterName}`);
        return graphData;
    }

    async getGraphNodes(): Promise<any[]> {
        const graphData = await this.waitForGraphData();

        let transformData: any = null;
        for (let attempt = 0; attempt < 3; attempt++) {
            await this.page.waitForTimeout(1000);

            transformData = await this.canvasElement.evaluate((canvas: HTMLCanvasElement) => {
                const rect = canvas.getBoundingClientRect();
                const ctx = canvas.getContext('2d');
                return {
                    left: rect.left,
                    top: rect.top,
                    width: rect.width,
                    height: rect.height,
                    canvasWidth: canvas.width,
                    canvasHeight: canvas.height,
                    transform: ctx?.getTransform() || null,
                };
            });

            if (transformData.transform) break;
            console.warn(`Attempt ${attempt + 1}: Transform data not available, retrying...`);
        }

        if (!transformData?.transform) throw new Error("Canvas transform data not available!");

        // Support both data structures: { nodes } or { elements: { nodes } }
        const nodes = graphData.elements?.nodes || graphData.nodes;
        if (!nodes) throw new Error("No nodes found in graph data!");

        const { a, b, c, d, e, f } = transformData.transform;
        const cssScaleX = transformData.canvasWidth ? transformData.width / transformData.canvasWidth : 1;
        const cssScaleY = transformData.canvasHeight ? transformData.height / transformData.canvasHeight : 1;
        return nodes.map((node: any) => {
            const relativeX = (node.x * a + node.y * c + e) * cssScaleX;
            const relativeY = (node.x * b + node.y * d + f) * cssScaleY;
            // Canvas format has properties nested in 'data' object and 'labels' instead of 'category'
            // Flatten the structure for backward compatibility
            const flatNode = {
                ...node,
                ...(node.data || {}), // Spread data properties to top level
                category: node.labels?.[0] || node.category, // Use labels[0] or fallback to category
                screenX: transformData.left + relativeX,
                screenY: transformData.top + relativeY,
            };
            return flatNode;
        });
    }


    async getCanvasScaling(): Promise<{ scaleX: number; scaleY: number }> {
        await this.waitForCanvasAnimationToEnd();
        const zoom = await this.canvasHost.evaluate((canvas: any) => {
            return typeof canvas.getZoom === "function" ? canvas.getZoom() : 1;
        });
        return { scaleX: zoom, scaleY: zoom };
    }

    async downloadImage(): Promise<Download> {
        await this.page.waitForLoadState('networkidle');
        const [download] = await Promise.all([
            this.page.waitForEvent('download'),
            interactWhenVisible(this.downloadImageBtn, (el) => el.click(), 'Download Image button'),
        ]);

        return download;
    }

    async rightClickAtCanvasCenter(): Promise<void> {
        await this.waitForCanvasAnimationToEnd();
        const boundingBox = await this.canvasElement.boundingBox();
        if (!boundingBox) throw new Error('Canvas bounding box not found');
        const centerX = boundingBox.x + boundingBox.width / 2;
        const centerY = boundingBox.y + boundingBox.height / 2;
        for (let attempt = 1; attempt <= 3; attempt++) {
            await this.page.mouse.move(centerX, centerY);
            await this.page.waitForTimeout(500);
            await this.page.mouse.click(centerX, centerY, { button: 'right' });
            // In focus mode the app centers the clicked element first and only
            // shows the menu ~400ms after the pan animation, so wait for it.
            const menuAppeared = await this.elementMenu
                .waitFor({ state: 'visible', timeout: 3000 })
                .then(() => true)
                .catch(() => false);
            if (menuAppeared) {
                return;
            }
            await this.page.waitForTimeout(1000);
        }
        throw new Error('Element menu not visible after right-clicking at canvas center');
    }

    async hoverAtCanvasCenter(): Promise<void> {
        const boundingBox = await this.canvasElement.boundingBox();
        if (!boundingBox) throw new Error('Canvas bounding box not found');
        const centerX = boundingBox.x + boundingBox.width / 2;
        const centerY = boundingBox.y + boundingBox.height / 2;
        await this.page.mouse.move(centerX, centerY);
    }

    async isNodeToolTipVisible(node: string): Promise<boolean> {
        return await waitForElementToBeVisible(this.nodeToolTip(node));
    }

    async getNodeToolTipContent(): Promise<string> {
        await waitForElementToBeVisible(this.canvasTooltip);
        return (await this.canvasTooltip.innerText()).trim();
    }

    async getGraphDetails(): Promise<any> {
        await this.canvasElementBeforeGraphSelection.waitFor({ state: 'detached' });
        return await this.waitForGraphData();
    }

    async waitForCanvasAnimationToEnd(timeout = 4500): Promise<void> {
        // Check if canvas exists before waiting for it
        const canvasContainer = this.page.locator("falkordb-canvas");
        const canvasCount = await canvasContainer.count();

        if (canvasCount === 0) {
            return;
        }

        // Wait for the canvas element to be attached
        await this.canvasElement.waitFor({ state: "attached", timeout: 10000 });
        const startTime = Date.now();
        while (Date.now() - startTime < timeout) {
            const status = await this.canvasElement.getAttribute("data-engine-status");
            if (status === "stopped") {
                return;
            }
            await this.page.waitForTimeout(500);
        }
        const finalStatus = await this.canvasElement.getAttribute("data-engine-status");
        if (finalStatus === "stopped") {
            return;
        }
        throw new Error(`Canvas animation did not stop within ${timeout}ms; final status: "${finalStatus}"`);
    }

    private async waitForCanvasViewportToSettle(timeout = 5000, interval = 250): Promise<void> {
        await this.canvasHost.waitFor({ state: "attached", timeout: 10000 });

        let previousZoom: number | null = null;
        let stableReads = 0;
        const startTime = Date.now();

        while (Date.now() - startTime < timeout) {
            const { cooldown, zoom } = await this.canvasHost.evaluate((canvas: any) => {
                const graph = typeof canvas.getGraph === "function" ? canvas.getGraph() : undefined;
                return {
                    cooldown: typeof graph?.cooldownTicks === "function" ? graph.cooldownTicks() : null,
                    zoom: typeof canvas.getZoom === "function" ? canvas.getZoom() : null,
                };
            });

            if (cooldown === 0 && typeof zoom === "number" && Number.isFinite(zoom)) {
                if (previousZoom !== null && Math.abs(zoom - previousZoom) < 0.0001) {
                    stableReads += 1;
                } else {
                    stableReads = 0;
                }

                previousZoom = zoom;

                if (stableReads >= 2) {
                    return;
                }
            } else {
                previousZoom = null;
                stableReads = 0;
            }

            await this.page.waitForTimeout(interval);
        }

        throw new Error("Canvas viewport did not settle after graph selection");
    }

    private async getActiveGraphData(): Promise<any | null> {
        return await this.page.evaluate((getterName) => {
            const getter = (window as any)[getterName];
            return typeof getter === "function" ? getter() : null;
        }, this.activeGraphGetterName);
    }

    private async getActiveGraphSnapshot(): Promise<{ graphId: string | null; nodeIds: string[] }> {
        return await this.page.evaluate((getterName) => {
            const getter = (window as any)[getterName];
            const graphData = typeof getter === "function" ? getter() : null;
            const nodes = graphData?.elements?.nodes || graphData?.nodes || [];

            return {
                graphId: (window as any).graph?.Id != null ? String((window as any).graph.Id) : null,
                nodeIds: Array.isArray(nodes) ? nodes.map((node: { id: string | number }) => String(node.id)).sort() : [],
            };
        }, this.activeGraphGetterName);
    }

    /* Element Menu specific tests */
    async isElementMenuVisible(): Promise<boolean> {
        await this.page.waitForTimeout(500);
        return await this.elementMenu.isVisible();
    }

    async getElementMenuBoundingBox(): Promise<any> {
        const isVisible = await this.isElementMenuVisible();
        if (!isVisible) throw new Error("Element menu is not visible!");
        return await this.elementMenu.boundingBox();
    }

    async hasElementMenuButton(buttonTitle: string): Promise<boolean> {
        const isVisible = await this.isElementMenuVisible();
        if (!isVisible) throw new Error("Element menu is not visible!");
        const button = this.elementMenuButton(buttonTitle);
        return await button.isVisible();
    }

    async rightClickAtNode(x: number, y: number): Promise<void> {
        await this.waitForCanvasAnimationToEnd();
        const boundingBox = await this.canvasElement.boundingBox();
        if (!boundingBox) throw new Error("Canvas bounding box not found");

        // Move to node position and right-click
        await this.page.mouse.move(x, y);
        await this.page.waitForTimeout(300);
        await this.page.mouse.click(x, y, { button: 'right' });
        
        // Wait for element menu to appear. In focus mode the app first centers
        // the clicked node (300ms pan) and shows the menu ~400ms later, so we
        // must actually wait for visibility rather than checking immediately.
        const isMenuVisible = await this.elementMenu
            .waitFor({ state: 'visible', timeout: 5000 })
            .then(() => true)
            .catch(() => false);
        if (!isMenuVisible) {
            throw new Error(`Element menu not visible after right-clicking at (${x}, ${y})`);
        }
    }

    async getCanvasBoundingBox(): Promise<any> {
        return await this.canvasElement.boundingBox();
    }
}
