const apiBaseUrlInput = document.getElementById('apiBaseUrl');
const categoryFilter = document.getElementById('categoryFilter');
const storyLimit = document.getElementById('storyLimit');
const refreshButton = document.getElementById('refreshButton');
const storiesContainer = document.getElementById('stories');
const statusEl = document.getElementById('status');
const cardTemplate = document.getElementById('storyCardTemplate');

const storiesByCategory = new Map();

function formatDate(value) {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function normalizeCategory(category) {
  return (category || 'uncategorized').trim();
}

function clearStories() {
  storiesContainer.innerHTML = '';
}

function renderStories(stories) {
  clearStories();

  if (!stories.length) {
    statusEl.textContent = 'No stories found for this filter.';
    return;
  }

  const selectedCategory = categoryFilter.value;
  const visibleStories = selectedCategory
    ? stories.filter((story) => normalizeCategory(story.category) === selectedCategory)
    : stories;

  if (!visibleStories.length) {
    statusEl.textContent = 'No stories match this category.';
    return;
  }

  statusEl.textContent = `Showing ${visibleStories.length} story${visibleStories.length === 1 ? '' : 'ies'}.`;

  const fragment = document.createDocumentFragment();
  for (const story of visibleStories) {
    const node = cardTemplate.content.cloneNode(true);
    const titleEl = node.querySelector('.story-title');
    const metaEl = node.querySelector('.story-meta');
    const explanationEl = node.querySelector('.story-explanation');
    const categoryEl = node.querySelector('.story-category');
    const linkEl = node.querySelector('.story-link');

    titleEl.textContent = story.title;
    metaEl.textContent = `${story.source} • Score ${Number(story.llm_score).toFixed(1)} • ${formatDate(story.timestamp)}`;
    explanationEl.textContent = story.explanation;
    categoryEl.textContent = normalizeCategory(story.category);
    linkEl.href = story.url;

    fragment.appendChild(node);
  }

  storiesContainer.appendChild(fragment);
}

function updateCategoryOptions(stories) {
  const categories = [...new Set(stories.map((story) => normalizeCategory(story.category)))].sort((a, b) =>
    a.localeCompare(b),
  );

  const currentValue = categoryFilter.value;
  categoryFilter.innerHTML = '<option value="">All categories</option>';

  for (const category of categories) {
    const option = document.createElement('option');
    option.value = category;
    option.textContent = category;
    categoryFilter.appendChild(option);
  }

  if (categories.includes(currentValue)) {
    categoryFilter.value = currentValue;
  }
}

async function fetchWeeklyStories() {
  const baseUrl = apiBaseUrlInput.value.replace(/\/$/, '');
  const limit = Number(storyLimit.value || 25);

  const endpoint = new URL(`${baseUrl}/week`);
  endpoint.searchParams.set('limit', String(limit));

  statusEl.textContent = 'Loading stories…';
  refreshButton.disabled = true;

  try {
    const response = await fetch(endpoint);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const stories = await response.json();
    storiesByCategory.clear();

    for (const story of stories) {
      const category = normalizeCategory(story.category);
      const bucket = storiesByCategory.get(category) || [];
      bucket.push(story);
      storiesByCategory.set(category, bucket);
    }

    updateCategoryOptions(stories);
    renderStories(stories);
  } catch (error) {
    clearStories();
    statusEl.textContent = `Could not load stories. Make sure the backend is running at ${baseUrl}. (${error.message})`;
  } finally {
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener('click', fetchWeeklyStories);
categoryFilter.addEventListener('change', () => {
  const mergedStories = [...storiesByCategory.values()].flat();
  renderStories(mergedStories);
});

fetchWeeklyStories();
