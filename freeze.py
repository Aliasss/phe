from flask_frozen import Freezer
from flask_frozen import MimetypeMismatchWarning
from main import app, db
import warnings
warnings.filterwarnings("ignore", category=MimetypeMismatchWarning)

freezer = Freezer(app)

@freezer.register_generator
def url_generator():
    # 정적으로 생성할 URL 목록
    yield '/'
    
    # 모든 게시물 URL 생성
    posts = db.collection('posts').stream()
    for post in posts:
        try:
            post_data = post.to_dict()
            if 'created_at' in post_data and isinstance(post_data['created_at'], datetime):
                yield f'/post/{post.id}'
            else:
                print(f"Skipping post {post.id} due to missing or incorrect 'created_at' field")
        except Exception as e:
            print(f"Error generating URL for post {post.id}: {str(e)}")

if __name__ == '__main__':
    try:
        freezer.freeze()
    except Exception as e:
        print(f"Error during freezing: {str(e)}")