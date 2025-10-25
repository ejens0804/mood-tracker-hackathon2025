const emotionImages = document.querySelectorAll('#emotion-grid img');

emotionImages.forEach(img => {
  img.style.cursor = 'pointer';
  img.addEventListener('click', () => {
    const emotion = img.alt || img.src.split('/').pop().split('-')[0];
    alert(`You clicked: ${emotion}`);
  });
});