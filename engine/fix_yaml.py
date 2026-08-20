import glob, re

for filepath in glob.glob('src/content/blog/*.md'):
    with open(filepath, 'r') as f:
        content = f.read()
    
    parts = content.split('---')
    if len(parts) >= 3:
        frontmatter = parts[1]
        
        # Keep only the FIRST occurrence of unsplashImage, imageCreditName, imageCreditUsername
        lines = frontmatter.split('\n')
        seen = set()
        new_lines = []
        for line in lines:
            if line.startswith('unsplashImage:'):
                if 'unsplashImage:' in seen: continue
                seen.add('unsplashImage:')
            elif line.startswith('imageCreditName:'):
                if 'imageCreditName:' in seen: continue
                seen.add('imageCreditName:')
            elif line.startswith('imageCreditUsername:'):
                if 'imageCreditUsername:' in seen: continue
                seen.add('imageCreditUsername:')
            new_lines.append(line)
        
        new_frontmatter = '\n'.join(new_lines)
        new_content = '---' + new_frontmatter + '---' + '---'.join(parts[2:])
        
        if new_content != content:
            with open(filepath, 'w') as f:
                f.write(new_content)
            print(f"Fixed {filepath}")
