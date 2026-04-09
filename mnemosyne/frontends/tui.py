from textual.app import App, ComposeResult
from textual.containers import VerticalScroll, Horizontal
from textual.widgets import Header, Footer, Input, Button, Markdown, Label, Static
from textual.reactive import reactive
from textual.binding import Binding
from textual.theme import Theme
from mnemosyne.agent.loop import run as agent_run
from mnemosyne.agent.schemas import WritePlan
from mnemosyne.db.connection import get_history, save_messages

VAULT_THEME = Theme(
    name="vault",
    primary="#4f98a3",
    secondary="#81A1C1",
    accent="#6daa45",
    foreground="#cdccca",
    background="#171614",
    success="#6daa45",
    warning="#fdab43",
    error="#dd6974",
    surface="#1c1b19",
    panel="#201f1d",
    dark=True,
)

class ChatMessage(Static):
    DEFAULT_CSS = """
    ChatMessage {
        padding: 0 1;
        margin-bottom: 1;
    }
    ChatMessage.user {
        color: $accent;
        border-left: thick $accent;
        padding-left: 1;
    }
    ChatMessage.assistant {
        color: $foreground;
    }
    ChatMessage.tool-call {
        color: $text-muted;
        opacity: 60%;
    }
    """

class WritePlanWidget(Static):
    DEFAULT_CSS = """
    WritePlanWidget {
        border: round $warning;
        padding: 1;
        margin: 1 0;
    }
    """

class ChatApp(App):
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+r", "reindex", "Reindex"),
        Binding("ctrl+l", "clear", "Clear chat"),
        Binding("escape", "reject_plan", "Reject plan"),
    ]
    CSS = """
    #conversation { height: 1fr; }
    #input-row { height: 3; dock: bottom; }
    #message-input { width: 1fr; }
    """

    pending_plans: reactive[list[WritePlan]] = reactive([], init=False)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield VerticalScroll(id="conversation")
        with Horizontal(id="input-row"):
            yield Input(placeholder="Ask anything about your vault...", id="message-input")
            yield Button("Send", variant="primary", id="send-btn")
        yield Footer()

    def on_mount(self):
        self.register_theme(VAULT_THEME)
        self.theme = "vault"
        self.query_one("#message-input").focus()

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "send-btn":
            await self._send_message()

    async def on_input_submitted(self, event: Input.Submitted):
        await self._send_message()

    async def _send_message(self):
        input_widget = self.query_one("#message-input", Input)
        message = input_widget.value.strip()
        if not message:
            return
        input_widget.value = ""
        input_widget.disabled = True
        conv = self.query_one("#conversation", VerticalScroll)
        conv.mount(ChatMessage(f"**You:** {message}", classes="user"))
        conv.scroll_end(animate=False)

        def do_agent():
            history = get_history("local")
            return agent_run(message, history)

        response = await self.run_in_thread(do_agent)
        save_messages("local", "tui", [
            {"role": "user", "content": message},
            {"role": "assistant", "content": response.text},
        ])

        if response.tool_calls_made:
            tool_line = "  ".join(f"[🔍 {t}]" for t in response.tool_calls_made)
            conv.mount(ChatMessage(tool_line, classes="tool-call"))

        conv.mount(ChatMessage(response.text, classes="assistant"))

        if response.write_plans:
            self.pending_plans = response.write_plans
            for plan in response.write_plans:
                widget = WritePlanWidget(
                    f"**Proposed: {plan.operation}** → `{plan.path}`\n\n"
                    f"```diff\n{plan.preview[:500]}\n```\n\n"
                    f"[Enter] to apply · [Escape] to reject"
                )
                conv.mount(widget)

        conv.scroll_end(animate=False)
        input_widget.disabled = False
        input_widget.focus()

    async def action_reindex(self):
        from mnemosyne.services import vault as v, index as idx, embed as emb
        from mnemosyne.db.connection import init_db
        conv = self.query_one("#conversation", VerticalScroll)
        conv.mount(ChatMessage("[dim]Reindexing vault...[/dim]", classes="tool-call"))
        def do_reindex():
            init_db()
            notes = v.crawl_vault()
            chunks = [c for note in notes for c in v.chunk_note(note)]
            idx.upsert_chunks(chunks)
            emb.ensure_collection()
            emb.index_chunks(chunks)
            return len(chunks)
        n = await self.run_in_thread(do_reindex)
        conv.mount(ChatMessage(f"[green]✓ Reindexed {n} chunks[/green]", classes="assistant"))
        conv.scroll_end(animate=False)

    async def action_clear(self):
        conv = self.query_one("#conversation", VerticalScroll)
        await conv.remove_children()

    async def on_key(self, event):
        if event.key == "enter" and self.pending_plans:
            from mnemosyne.services.writes import apply_plan
            plan = self.pending_plans
            result = apply_plan(plan)
            conv = self.query_one("#conversation", VerticalScroll)
            conv.mount(ChatMessage(f"[green]{result}[/green]", classes="assistant"))
            self.pending_plans = self.pending_plans[1:]
            conv.scroll_end(animate=False)

    def action_reject_plan(self):
        if self.pending_plans:
            self.pending_plans = []
            conv = self.query_one("#conversation", VerticalScroll)
            conv.mount(ChatMessage("[yellow]Write plan rejected.[/yellow]", classes="tool-call"))

def run_tui():
    app = ChatApp()
    app.run()
