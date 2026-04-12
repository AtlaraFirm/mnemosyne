from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.markup import MarkupError, escape
from textual.reactive import reactive
from textual.theme import Theme
from textual.widgets import Button, Footer, Header, Input, Static

from mnemosyne.agent.loop import run_stream as agent_run_stream
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
            yield Input(
                placeholder="Ask anything about your vault...", id="message-input"
            )
            yield Button("Send", variant="primary", id="send-btn")
        yield Footer()

    def on_mount(self):
        from mnemosyne.db.connection import init_db

        init_db()
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
        try:
            conv.mount(ChatMessage(f"**You:** {message}", classes="user"))
        except MarkupError:
            conv.mount(ChatMessage(escape(f"**You:** {message}"), classes="user"))
        conv.scroll_end(animate=False)

        try:
            history = get_history("local")
            content = ""
            msg_widget = ChatMessage("", classes="assistant")
            conv.mount(msg_widget)
            conv.scroll_end(animate=False)

            async def update_content(new_content):
                try:
                    msg_widget.update(new_content)
                except MarkupError:
                    msg_widget.update(escape(new_content))
                conv.scroll_end(animate=False)

            # Use async for for streaming agent
            async for chunk in agent_run_stream(message, history):
                if chunk["type"] == "content":
                    content = chunk["content"]
                    await update_content(content)
                elif chunk["type"] == "tool_call":
                    tool_line = "  ".join(
                        f"[🔍 {t.get('function', {}).get('name', '?')}]"
                        for t in chunk["tool_calls"]
                    )
                    try:
                        conv.mount(ChatMessage(tool_line, classes="tool-call"))
                    except MarkupError:
                        conv.mount(ChatMessage(escape(tool_line), classes="tool-call"))
                    conv.scroll_end(animate=False)
                elif chunk["type"] == "done":
                    break
            save_messages(
                "local",
                "tui",
                [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": content},
                ],
            )
        except Exception as e:
            conv.mount(ChatMessage(f"[red]Error: {e}[/red]", classes="error"))
        finally:
            input_widget.disabled = False
            input_widget.focus()

    async def action_reindex(self):
        from mnemosyne.db.connection import init_db
        from mnemosyne.services import embed as emb
        from mnemosyne.services import index as idx
        from mnemosyne.services import vault as v

        conv = self.query_one("#conversation", VerticalScroll)
        try:
            conv.mount(
                ChatMessage("[dim]Reindexing vault...[/dim]", classes="tool-call")
            )
        except MarkupError:
            conv.mount(ChatMessage(escape("Reindexing vault..."), classes="tool-call"))

        def do_reindex():
            init_db()
            notes = v.crawl_vault()
            chunks = [c for note in notes for c in v.chunk_note(note)]
            idx.upsert_chunks(chunks)
            emb.ensure_collection()
            emb.index_chunks(chunks)
            return len(chunks)

        n = do_reindex()
        try:
            conv.mount(
                ChatMessage(
                    f"[green]✓ Reindexed {n} chunks[/green]", classes="assistant"
                )
            )
        except MarkupError:
            conv.mount(
                ChatMessage(escape(f"✓ Reindexed {n} chunks"), classes="assistant")
            )
        conv.scroll_end(animate=False)

    async def action_clear(self):
        conv = self.query_one("#conversation", VerticalScroll)
        await conv.remove_children()
        input_widget = self.query_one("#message-input", Input)
        input_widget.value = ""
        input_widget.focus()

    async def on_key(self, event):
        if event.key == "enter" and self.pending_plans:
            from mnemosyne.services.writes import apply_plan

            plan = self.pending_plans
            result = apply_plan(plan)
            conv = self.query_one("#conversation", VerticalScroll)
            try:
                conv.mount(ChatMessage(f"[green]{result}[/green]", classes="assistant"))
            except MarkupError:
                conv.mount(ChatMessage(escape(str(result)), classes="assistant"))
            self.pending_plans = self.pending_plans[1:]
            conv.scroll_end(animate=False)

    def action_reject_plan(self):
        if self.pending_plans:
            self.pending_plans = []
            conv = self.query_one("#conversation", VerticalScroll)
            try:
                conv.mount(
                    ChatMessage(
                        "[yellow]Write plan rejected.[/yellow]", classes="tool-call"
                    )
                )
            except MarkupError:
                conv.mount(
                    ChatMessage(escape("Write plan rejected."), classes="tool-call")
                )


def run_tui():
    app = ChatApp()
    app.run()

if __name__ == "__main__":
    run_tui()


