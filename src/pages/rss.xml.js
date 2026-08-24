import { getCollection } from 'astro:content';
import rss from '@astrojs/rss';
import { SITE_DESCRIPTION, SITE_TITLE } from '../consts';

export async function GET(context) {
	const now = new Date();
	const posts = (await getCollection('blog')).filter(post => post.data.pubDate <= now);
	return rss({
		title: SITE_TITLE,
		description: SITE_DESCRIPTION,
		site: context.site,
		xmlns: { media: 'http://search.yahoo.com/mrss/' },
		items: posts.map((post) => {
			const imageUrl = post.data.unsplashImage || (post.data.heroImage ? new URL(post.data.heroImage.src, context.site).toString() : null);
			const customData = imageUrl ? `<media:content type="image/jpeg" medium="image" url="${imageUrl}" />` : '';
			
			return {
				title: post.data.title,
				pubDate: post.data.pubDate,
				description: post.data.description || post.data.title,
				link: `/blog/${post.id}/`,
				customData,
			};
		}),
	});
}
