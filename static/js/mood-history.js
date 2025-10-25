document.addEventListener('DOMContentLoaded', () => {
  const collapsibleRows = document.querySelectorAll('tr.collapsible');

  collapsibleRows.forEach(row => {
    row.style.cursor = 'pointer'; // indicate clickability

    row.addEventListener('click', () => {
      const next = row.nextElementSibling;
      if (next && next.classList.contains('details')) {
        next.classList.toggle('show');
      }
    });
  });
});