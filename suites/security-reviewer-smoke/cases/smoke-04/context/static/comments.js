export function renderComments(list, comments) {
  list.replaceChildren();
  for (const c of comments) {
    const item = document.createElement("li");
    item.innerHTML = `<b>${c.author}</b>: ${c.body}`;
    list.append(item);
  }
}
