export function renderComments(list, comments, counter) {
  list.replaceChildren();
  for (const c of comments) {
    const item = document.createElement("li");
    const author = document.createElement("b");
    author.textContent = c.author;
    item.append(author, `: ${c.body}`);
    list.append(item);
  }
  if (counter) {
    counter.textContent = `${comments.length} comment${comments.length === 1 ? "" : "s"}`;
  }
}
