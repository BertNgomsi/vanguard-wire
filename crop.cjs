const fs = require('fs');
try {
  const sharp = require('sharp');
  sharp('public/logo.jpg')
    .extract({ width: 1080, height: 600, left: 0, top: 120 })
    .toFile('public/logo_cropped.jpg')
    .then(() => {
      fs.renameSync('public/logo_cropped.jpg', 'public/logo.jpg');
      console.log('Cropped successfully with sharp');
    })
    .catch(err => console.error('Sharp error:', err));
} catch (e) {
  console.log('Sharp not found');
}
