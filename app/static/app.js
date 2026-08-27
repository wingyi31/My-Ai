"use strict";

const messages = document.querySelector(
  "#messages"
);
const chatForm = document.querySelector(
  "#chat-form"
);
const messageInput = document.querySelector(
  "#message-input"
);
const sendButton = document.querySelector(
  "#send-button"
);
const userIdInput = document.querySelector(
  "#user-id"
);
const courseIdInput = document.querySelector(
  "#course-id"
);

function scrollToBottom() {
  messages.scrollTop = messages.scrollHeight;
}

function createElement(
  tag,
  className,
  text
) {
  const element = document.createElement(tag);

  if (className) {
    element.className = className;
  }

  if (text !== undefined) {
    element.textContent = text;
  }

  return element;
}

function appendInlineText(
  container,
  text
) {
  const pattern =
    /(\*\*[^*]+\*\*|\[Source \d+\])/g;

  let previousIndex = 0;

  for (const match of text.matchAll(pattern)) {
    if (match.index > previousIndex) {
      container.append(
        document.createTextNode(
          text.slice(
            previousIndex,
            match.index
          )
        )
      );
    }

    const value = match[0];

    if (value.startsWith("**")) {
      const strong =
        document.createElement("strong");

      strong.textContent = value.slice(2, -2);
      container.append(strong);
    } else {
      container.append(
        createElement(
          "span",
          "citation",
          value
        )
      );
    }

    previousIndex =
      match.index + value.length;
  }

  if (previousIndex < text.length) {
    container.append(
      document.createTextNode(
        text.slice(previousIndex)
      )
    );
  }
}

function renderAnswer(
  container,
  text
) {
  const lines = text.split("\n");
  let activeList = null;

  for (const rawLine of lines) {
    const line = rawLine.trim();

    if (!line) {
      activeList = null;
      continue;
    }

    const bulletMatch = line.match(
      /^[-*]\s+(.+)$/
    );

    if (bulletMatch) {
      if (!activeList) {
        activeList =
          document.createElement("ul");
        container.append(activeList);
      }

      const item =
        document.createElement("li");

      appendInlineText(
        item,
        bulletMatch[1]
      );
      activeList.append(item);
      continue;
    }

    activeList = null;

    const paragraph =
      document.createElement("p");

    appendInlineText(paragraph, line);
    container.append(paragraph);
  }
}

function createMessageShell(
  role,
  isError = false
) {
  const article = createElement(
    "article",
    [
      "message",
      role === "user"
        ? "user-message"
        : "assistant-message",
      isError ? "error-message" : "",
    ]
      .filter(Boolean)
      .join(" ")
  );

  const avatar = createElement(
    "div",
    "avatar",
    role === "user" ? "Y" : "S"
  );

  const body = createElement(
    "div",
    "message-body"
  );

  const label = createElement(
    "div",
    "message-label",
    role === "user" ? "You" : "StudyOps"
  );

  const content = createElement(
    "div",
    "message-content"
  );

  body.append(label, content);
  article.append(avatar, body);

  return {
    article,
    body,
    content,
  };
}

function appendUserMessage(text) {
  const shell = createMessageShell("user");
  const paragraph =
    document.createElement("p");

  paragraph.textContent = text;
  shell.content.append(paragraph);
  messages.append(shell.article);
  scrollToBottom();
}

function appendLoadingMessage() {
  const shell =
    createMessageShell("assistant");

  const dots = createElement(
    "div",
    "loading-dots"
  );

  dots.append(
    document.createElement("span"),
    document.createElement("span"),
    document.createElement("span")
  );

  shell.content.append(dots);
  messages.append(shell.article);
  scrollToBottom();

  return shell.article;
}

function appendErrorMessage(message) {
  const shell = createMessageShell(
    "assistant",
    true
  );

  const paragraph =
    document.createElement("p");

  paragraph.textContent = message;
  shell.content.append(paragraph);
  messages.append(shell.article);
  scrollToBottom();
}

function addMetadata(
  body,
  response
) {
  const metadata = createElement(
    "div",
    "message-meta"
  );

  metadata.append(
    createElement(
      "span",
      "badge",
      response.generation_model
    )
  );

  for (
    const toolCall
    of response.tool_calls || []
  ) {
    metadata.append(
      createElement(
        "span",
        "badge",
        `Tool · ${toolCall.name}`
      )
    );
  }

  body.append(metadata);

  if (
    response.tool_calls
    && response.tool_calls.length
  ) {
    const details = createElement(
      "details",
      "tool-details"
    );
    const summary =
      document.createElement("summary");
    const pre =
      document.createElement("pre");

    summary.textContent =
      "Inspect tool trace";
    pre.textContent = JSON.stringify(
      response.tool_calls,
      null,
      2
    );

    details.append(summary, pre);
    body.append(details);
  }
}

function addSources(
  body,
  sources
) {
  if (!sources || !sources.length) {
    return;
  }

  const container = createElement(
    "div",
    "sources"
  );

  for (const source of sources) {
    const card = createElement(
      "div",
      "source-card"
    );

    const title = createElement(
      "div",
      "source-title",
      `Source ${source.source_number} · ` +
        source.filename
    );

    const page =
      source.page_number ?? "Unknown";

    const similarity =
      Number(source.similarity).toFixed(3);

    const meta = createElement(
      "div",
      "source-meta",
      `Page ${page} · Similarity ${similarity}`
    );

    card.append(title, meta);
    container.append(card);
  }

  body.append(container);
}

function formatDate(value) {
  if (!value) {
    return "Not provided";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString(
    undefined,
    {
      dateStyle: "medium",
      timeStyle: "medium",
    }
  );
}

async function requestJson(
  url,
  options
) {
  const response = await fetch(
    url,
    options
  );

  let payload;

  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const detail =
      payload && payload.detail
        ? payload.detail
        : `Request failed with status ` +
          response.status;

    throw new Error(detail);
  }

  return payload;
}

function addPendingAction(
  body,
  action
) {
  if (!action) {
    return;
  }

  const card = createElement(
    "section",
    "action-card"
  );

  const header = createElement(
    "div",
    "action-header"
  );
  const heading = createElement(
    "h3",
    "",
    "Calendar proposal"
  );
  const status = createElement(
    "span",
    "action-status",
    action.status
  );

  header.append(heading, status);

  const event = action.event || {};
  const grid =
    document.createElement("dl");

  grid.className = "action-grid";

  const fields = [
    [
      "Event",
      event.summary || "Untitled",
    ],
    [
      "Starts",
      formatDate(
        event.start &&
          event.start.dateTime
      ),
    ],
    [
      "Ends",
      formatDate(
        event.end &&
          event.end.dateTime
      ),
    ],
    [
      "Expires",
      formatDate(action.expires_at),
    ],
  ];

  for (const [label, value] of fields) {
    grid.append(
      createElement("dt", "", label),
      createElement("dd", "", value)
    );
  }

  const buttons = createElement(
    "div",
    "action-buttons"
  );

  const confirmButton = createElement(
    "button",
    "confirm-button",
    "Confirm event"
  );
  const cancelButton = createElement(
    "button",
    "cancel-button",
    "Cancel"
  );

  confirmButton.type = "button";
  cancelButton.type = "button";

  const resultText = createElement(
    "div",
    "action-success"
  );

  async function disableActions() {
    confirmButton.disabled = true;
    cancelButton.disabled = true;
  }

  confirmButton.addEventListener(
    "click",
    async () => {
      disableActions();
      resultText.textContent =
        "Creating Calendar event…";

      try {
        const response =
          await requestJson(
            `/api/v1/agent/actions/` +
              `${encodeURIComponent(
                action.action_id
              )}/confirm`,
            {
              method: "POST",
              headers: {
                "Content-Type":
                  "application/json",
              },
              body: JSON.stringify({
                user_id:
                  userIdInput.value.trim(),
              }),
            }
          );

        status.textContent =
          response.status;

        resultText.textContent =
          response.already_completed
            ? "Event was already created."
            : "Calendar event created.";

        const link =
          response.action
            .calendar_event_link;

        if (link) {
          const anchor =
            document.createElement("a");

          anchor.href = link;
          anchor.target = "_blank";
          anchor.rel = "noopener noreferrer";
          anchor.textContent =
            " Open in Google Calendar";

          resultText.append(anchor);
        }
      } catch (error) {
        confirmButton.disabled = false;
        cancelButton.disabled = false;
        resultText.textContent =
          error.message;
      }
    }
  );

  cancelButton.addEventListener(
    "click",
    async () => {
      disableActions();
      resultText.textContent =
        "Cancelling proposal…";

      try {
        await requestJson(
          `/api/v1/agent/actions/` +
            `${encodeURIComponent(
              action.action_id
            )}/cancel`,
          {
            method: "POST",
            headers: {
              "Content-Type":
                "application/json",
            },
            body: JSON.stringify({
              user_id:
                userIdInput.value.trim(),
            }),
          }
        );

        status.textContent = "cancelled";
        resultText.textContent =
          "Proposal cancelled.";
      } catch (error) {
        confirmButton.disabled = false;
        cancelButton.disabled = false;
        resultText.textContent =
          error.message;
      }
    }
  );

  buttons.append(
    confirmButton,
    cancelButton
  );

  card.append(
    header,
    grid,
    buttons,
    resultText
  );

  body.append(card);
}

function appendAssistantResponse(
  response
) {
  const shell =
    createMessageShell("assistant");

  renderAnswer(
    shell.content,
    response.answer
  );

  addMetadata(shell.body, response);
  addSources(
    shell.body,
    response.sources
  );
  addPendingAction(
    shell.body,
    response.pending_action
  );

  messages.append(shell.article);
  scrollToBottom();
}

function resizeComposer() {
  messageInput.style.height = "auto";
  messageInput.style.height =
    `${Math.min(
      messageInput.scrollHeight,
      160
    )}px`;
}

async function sendMessage(text) {
  const userId =
    userIdInput.value.trim();
  const courseId =
    courseIdInput.value.trim();

  if (!userId || !courseId) {
    appendErrorMessage(
      "Enter both a Canvas user ID " +
      "and course ID."
    );
    return;
  }

  appendUserMessage(text);
  const loading =
    appendLoadingMessage();

  sendButton.disabled = true;
  messageInput.disabled = true;

  try {
    const response = await requestJson(
      "/api/v1/agent/chat",
      {
        method: "POST",
        headers: {
          "Content-Type":
            "application/json",
        },
        body: JSON.stringify({
          user_id: userId,
          course_id: courseId,
          message: text,
          source_limit: 5,
        }),
      }
    );

    loading.remove();
    appendAssistantResponse(response);
  } catch (error) {
    loading.remove();
    appendErrorMessage(error.message);
  } finally {
    sendButton.disabled = false;
    messageInput.disabled = false;
    messageInput.focus();
  }
}

chatForm.addEventListener(
  "submit",
  async (event) => {
    event.preventDefault();

    const text =
      messageInput.value.trim();

    if (!text) {
      return;
    }

    messageInput.value = "";
    resizeComposer();
    await sendMessage(text);
  }
);

messageInput.addEventListener(
  "input",
  resizeComposer
);

messageInput.addEventListener(
  "keydown",
  (event) => {
    if (
      event.key === "Enter"
      && !event.shiftKey
    ) {
      event.preventDefault();
      chatForm.requestSubmit();
    }
  }
);

for (
  const button
  of document.querySelectorAll(
    ".quick-prompt"
  )
) {
  button.addEventListener(
    "click",
    () => {
      messageInput.value =
        button.dataset.prompt || "";
      resizeComposer();
      messageInput.focus();
    }
  );
}

messageInput.focus();