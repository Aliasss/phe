from flask import Flask, request, render_template, redirect, url_for, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import os
import jwt
from functools import wraps
from config import Config
import logging

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
CORS(app)
app.config.from_object(Config)
app.secret_key = os.urandom(24)
# app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')

# Firebase 초기화 코드
cred = credentials.Certificate('/Users/dongseob/Desktop/github/phe/phe/community-test-9a140-firebase-adminsdk-g7m9p-9ad858b701.json')  # 서비스 계정 키 JSON 파일 경로
firebase_admin.initialize_app(cred)

# Firestore 클라이언트 초기화
db = firestore.client()

# JWT 토큰 생성
def create_token():
    token = jwt.encode({'user_id': os.urandom(16).hex(), 'exp': datetime.utcnow() + timedelta(days=1)}, app.config['SECRET_KEY'], algorithm='HS256')
    return token

# JWT 토큰 검증 데코레이터
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get('token')
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        except:
            return jsonify({'message': 'Token is invalid!'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def home():
    try:
        # Firestore에서 모든 게시글 가져오기
        docs = db.collection('posts').order_by('created_at', direction=firestore.Query.DESCENDING).stream()
        posts = []

        for doc in docs:
            post_data = doc.to_dict()
            created_at = post_data.get('created_at')

            if isinstance(created_at, datetime):
                formatted_date = created_at
            else:
                # 문자열의 경우 datetime 객체로 변환
                formatted_date = datetime.fromisoformat(created_at)

            posts.append({
                'id': doc.id, 
                'title': post_data.get('title', '제목 없음'), 
                'content': post_data.get('content', '내용 없음'),
                'created_at': formatted_date,
                'has_password': post_data.get('has_password', False)
            })

        return render_template('index.html', posts=posts)

    except Exception as e:
        app.logger.error(f"Error in home: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/posts', methods=['POST'])
@token_required
def create_post():
    try:
        data = request.json
        post_title = data.get('title', '')
        post_content = data.get('content', '')
        post_password = data.get('password', '')
        
        token = request.cookies.get('token')
        user_data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        
        post = {
            'title': post_title,
            'content': post_content,
            'created_at': datetime.now(),
            'has_password': bool(post_password),
            'user_id': user_data['user_id']
        }
        
        # Firestore에 데이터 추가
        doc_ref = db.collection('posts').add(post)
        post_id = doc_ref[1].id
        
        # 비밀번호가 있는 경우, 별도의 컬렉션에 저장
        if post_password:
            db.collection('post_passwords').document(post_id).set({'password': post_password})
        
        return jsonify({'success': True, 'post_id': post_id}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/post/<post_id>')
def view_post(post_id):
    try:
        post_ref = db.collection('posts').document(post_id)
        post = post_ref.get()
        
        if post.exists:
            post_data = post.to_dict()
            post_data['id'] = post_id
            
            # created_at 필드가 없거나 잘못된 형식인 경우 처리
            if 'created_at' not in post_data or not isinstance(post_data['created_at'], datetime):
                post_data['created_at'] = datetime.now()  # 기본값 설정
            
            current_user_id = None  # 현재 사용자 ID 설정 (필요한 경우)
            return render_template('post.html', post=post_data, current_user_id=current_user_id)
        else:
            return redirect(url_for('home'))
    except Exception as e:
        app.logger.error(f"Error in view_post: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

# @app.route('/post/<post_id>')
# def view_post(post_id):
#     try:
#         # Frozen-Flask를 위한 더미 데이터
#         if app.config.get('FREEZER_REALTIVE_URLS', False):
#             post_data = {
#                 'title': 'Dummy Title',
#                 'content': 'Dummy Content',
#                 'created_at': datetime.now(),
#                 'id': post_id
#             }
#             return render_template('post.html', post=post_data, current_user_id=None)
        
#         post_ref = db.collection('posts').document(post_id)
#         post = post_ref.get()
        
#         if post.exists:
#             post_data = post.to_dict()
#             post_data['id'] = post_id
#             token = request.cookies.get('token')
#             current_user_id = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])['user_id'] if token else None
#             return render_template('post.html', post=post_data, current_user_id=current_user_id)
#         else:
#             return redirect(url_for('home'))

#     except Exception as e:
#         app.logger.error(f"Error in view_post: {str(e)}")
#         return jsonify({"error": "Internal server error"}), 500

@app.route('/api/posts/<post_id>', methods=['DELETE'])
@token_required
def delete_post(post_id):
    try:
        post_ref = db.collection('posts').document(post_id)
        post = post_ref.get()
        
        if post.exists:
            post_data = post.to_dict()
            token = request.cookies.get('token')
            current_user_id = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])['user_id']
            
            if post_data.get('has_password'):
                password = request.json.get('password')
                stored_password = db.collection('post_passwords').document(post_id).get().to_dict()['password']
                if password != stored_password:
                    return jsonify({"success": False, "error": "비밀번호가 일치하지 않습니다."}), 403
            elif current_user_id != post_data.get('user_id'):
                return jsonify({"success": False, "error": "삭제 권한이 없습니다."}), 403
            
            # 비밀번호가 일치하거나 비밀번호가 없는 경우
            post_ref.delete()
            if post_data.get('has_password'):
                db.collection('post_passwords').document(post_id).delete()
            return jsonify({"success": True}), 200
        else:
            return jsonify({"success": False, "error": "게시글을 찾을 수 없습니다."}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/edit/<post_id>', methods=['GET', 'POST'])
# @token_required
def edit_post(post_id):
    post_ref = db.collection('posts').document(post_id)
    post = post_ref.get()
    
    if not post.exists:
        return redirect(url_for('home'))
    
    post_data = post.to_dict()
    post_data['id'] = post_id
    
    if request.method == 'POST':
        token = request.cookies.get('token')
        current_user_id = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])['user_id']
        
        if post_data.get('has_password'):
            password = request.form.get('password')
            stored_password = db.collection('post_passwords').document(post_id).get().to_dict()['password']
            if password != stored_password:
                return render_template('edit_post.html', post=post_data, error="비밀번호가 일치하지 않습니다.")
        elif current_user_id != post_data.get('user_id'):
            return render_template('edit_post.html', post=post_data, error="수정 권한이 없습니다.")
        
        # 비밀번호가 일치하거나 비밀번호가 없는 경우
        post_ref.update({
            'title': request.form.get('title'),
            'content': request.form.get('content')
        })
        return redirect(url_for('view_post', post_id=post_id))
    
    return render_template('edit_post.html', post=post_data)

@app.route('/api/token', methods=['GET'])
def get_token():
    token = create_token()
    response = jsonify({'token': token})
    response.set_cookie('token', token, httponly=True, secure=True, samesite='Strict')
    return response

@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)


# from flask import Flask, request, render_template, redirect, url_for, jsonify
# import firebase_admin
# from firebase_admin import credentials, firestore
# from datetime import datetime, timedelta
# import os
# import jwt
# from functools import wraps

# app = Flask(__name__)
# app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')

# # Firebase 초기화 코드
# cred = credentials.Certificate('/Users/dongseob/Desktop/github/phe/phe/community-test-9a140-firebase-adminsdk-g7m9p-9ad858b701.json')  # 서비스 계정 키 JSON 파일 경로
# firebase_admin.initialize_app(cred)

# # Firestore 클라이언트 초기화
# db = firestore.client()

# # JWT 토큰 생성
# def create_token():
#     token = jwt.encode({'user_id': os.urandom(16).hex(), 'exp': datetime.utcnow() + timedelta(days=1)}, app.config['SECRET_KEY'], algorithm='HS256')
#     return token

# # JWT 토큰 검증 데코레이터
# def token_required(f):
#     @wraps(f)
#     def decorated(*args, **kwargs):
#         token = request.cookies.get('token')
#         if not token:
#             return jsonify({'message': 'Token is missing!'}), 401
#         try:
#             data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
#         except:
#             return jsonify({'message': 'Token is invalid!'}), 401
#         return f(*args, **kwargs)
#     return decorated

# @app.route('/')
# def home():
#     # Firestore에서 모든 게시글 가져오기
#     docs = db.collection('posts').order_by('created_at', direction=firestore.Query.DESCENDING).stream()
#     posts = []

#     for doc in docs:
#         post_data = doc.to_dict()
#         created_at = post_data.get('created_at')

#         if isinstance(created_at, datetime):
#             formatted_date = created_at
#         else:
#             # 문자열의 경우 datetime 객체로 변환
#             formatted_date = datetime.fromisoformat(created_at)

#         posts.append({
#             'id': doc.id, 
#             'title': post_data.get('title', '제목 없음'), 
#             'content': post_data.get('content', '내용 없음'),
#             'created_at': formatted_date,
#             'has_password': post_data.get('has_password', False)
#         })

#     return render_template('index.html', posts=posts)

# @app.route('/api/posts', methods=['POST'])
# @token_required
# def create_post():
#     data = request.json
#     post_title = data.get('title', '')
#     post_content = data.get('content', '')
#     post_password = data.get('password', '')
    
#     token = request.cookies.get('token')
#     user_data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
    
#     post = {
#         'title': post_title,
#         'content': post_content,
#         'created_at': datetime.now(),
#         'has_password': bool(post_password),
#         'user_id': user_data['user_id']
#     }
    
#     # Firestore에 데이터 추가
#     doc_ref = db.collection('posts').add(post)
#     post_id = doc_ref[1].id
    
#     # 비밀번호가 있는 경우, 별도의 컬렉션에 저장
#     if post_password:
#         db.collection('post_passwords').document(post_id).set({'password': post_password})
    
#     return jsonify({'success': True, 'post_id': post_id}), 201

# @app.route('/post/<post_id>')
# def view_post(post_id):
#     post_ref = db.collection('posts').document(post_id)
#     post = post_ref.get()
    
#     if post.exists:
#         post_data = post.to_dict()
#         post_data['id'] = post_id
#         token = request.cookies.get('token')
#         current_user_id = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])['user_id'] if token else None
#         return render_template('post.html', post=post_data, current_user_id=current_user_id)
#     else:
#         return redirect(url_for('home'))

# @app.route('/api/posts/<post_id>', methods=['DELETE'])
# @token_required
# def delete_post(post_id):
#     try:
#         post_ref = db.collection('posts').document(post_id)
#         post = post_ref.get()
        
#         if post.exists:
#             post_data = post.to_dict()
#             token = request.cookies.get('token')
#             current_user_id = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])['user_id']
            
#             if post_data.get('has_password'):
#                 password = request.json.get('password')
#                 stored_password = db.collection('post_passwords').document(post_id).get().to_dict()['password']
#                 if password != stored_password:
#                     return jsonify({"success": False, "error": "비밀번호가 일치하지 않습니다."}), 403
#             elif current_user_id != post_data.get('user_id'):
#                 return jsonify({"success": False, "error": "삭제 권한이 없습니다."}), 403
            
#             # 비밀번호가 일치하거나 비밀번호가 없는 경우
#             post_ref.delete()
#             if post_data.get('has_password'):
#                 db.collection('post_passwords').document(post_id).delete()
#             return jsonify({"success": True}), 200
#         else:
#             return jsonify({"success": False, "error": "게시글을 찾을 수 없습니다."}), 404
#     except Exception as e:
#         return jsonify({"success": False, "error": str(e)}), 500

# @app.route('/edit/<post_id>', methods=['GET', 'POST'])
# @token_required
# def edit_post(post_id):
#     post_ref = db.collection('posts').document(post_id)
#     post = post_ref.get()
    
#     if not post.exists:
#         return redirect(url_for('home'))
    
#     post_data = post.to_dict()
#     post_data['id'] = post_id
    
#     if request.method == 'POST':
#         token = request.cookies.get('token')
#         current_user_id = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])['user_id']
        
#         if post_data.get('has_password'):
#             password = request.form.get('password')
#             stored_password = db.collection('post_passwords').document(post_id).get().to_dict()['password']
#             if password != stored_password:
#                 return render_template('edit_post.html', post=post_data, error="비밀번호가 일치하지 않습니다.")
#         elif current_user_id != post_data.get('user_id'):
#             return render_template('edit_post.html', post=post_data, error="수정 권한이 없습니다.")
        
#         # 비밀번호가 일치하거나 비밀번호가 없는 경우
#         post_ref.update({
#             'title': request.form.get('title'),
#             'content': request.form.get('content')
#         })
#         return redirect(url_for('view_post', post_id=post_id))
    
#     return render_template('edit_post.html', post=post_data)

# @app.route('/api/token', methods=['GET'])
# def get_token():
#     token = create_token()
#     response = jsonify({'token': token})
#     response.set_cookie('token', token, httponly=True, secure=True, samesite='Strict')
#     return response

# if __name__ == '__main__':
#     app.run(debug=True)


# from flask import Flask, request, render_template, redirect, url_for, jsonify
# import firebase_admin
# from firebase_admin import credentials, firestore
# from datetime import datetime, timedelta
# import os
# import jwt
# from functools import wraps

# app = Flask(__name__)
# app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')

# # Firebase 초기화 코드
# cred = credentials.Certificate(os.environ.get('FIREBASE_CREDENTIALS', 'path/to/serviceAccountKey.json'))
# firebase_admin.initialize_app(cred)

# # Firestore 클라이언트 초기화
# db = firestore.client()

# # JWT 토큰 생성
# def create_token():
#     token = jwt.encode({'user_id': os.urandom(16).hex(), 'exp': datetime.utcnow() + timedelta(days=1)}, app.config['SECRET_KEY'], algorithm='HS256')
#     return token

# # JWT 토큰 검증 데코레이터
# def token_required(f):
#     @wraps(f)
#     def decorated(*args, **kwargs):
#         token = request.cookies.get('token')
#         if not token:
#             return jsonify({'message': 'Token is missing!'}), 401
#         try:
#             data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
#         except:
#             return jsonify({'message': 'Token is invalid!'}), 401
#         return f(*args, **kwargs)
#     return decorated

# @app.route('/')
# def home():
#     # Firestore에서 모든 게시글 가져오기
#     docs = db.collection('posts').order_by('created_at', direction=firestore.Query.DESCENDING).stream()
#     posts = []

#     for doc in docs:
#         post_data = doc.to_dict()
#         created_at = post_data.get('created_at')

#         if isinstance(created_at, datetime):
#             formatted_date = created_at
#         else:
#             # 문자열의 경우 datetime 객체로 변환
#             formatted_date = datetime.fromisoformat(created_at)

#         posts.append({
#             'id': doc.id, 
#             'title': post_data.get('title', '제목 없음'), 
#             'content': post_data.get('content', '내용 없음'),
#             'created_at': formatted_date,
#             'has_password': post_data.get('has_password', False)
#         })

#     return render_template('index.html', posts=posts)

# @app.route('/api/posts', methods=['POST'])
# @token_required
# def create_post():
#     data = request.json
#     post_title = data.get('title', '')
#     post_content = data.get('content', '')
#     post_password = data.get('password', '')
    
#     token = request.cookies.get('token')
#     user_data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
    
#     post = {
#         'title': post_title,
#         'content': post_content,
#         'created_at': datetime.now(),
#         'has_password': bool(post_password),
#         'user_id': user_data['user_id']
#     }
    
#     # Firestore에 데이터 추가
#     doc_ref = db.collection('posts').add(post)
#     post_id = doc_ref[1].id
    
#     # 비밀번호가 있는 경우, 별도의 컬렉션에 저장
#     if post_password:
#         db.collection('post_passwords').document(post_id).set({'password': post_password})
    
#     return jsonify({'success': True, 'post_id': post_id}), 201

# @app.route('/post/<post_id>')
# def view_post(post_id):
#     post_ref = db.collection('posts').document(post_id)
#     post = post_ref.get()
    
#     if post.exists:
#         post_data = post.to_dict()
#         post_data['id'] = post_id
#         token = request.cookies.get('token')
#         current_user_id = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])['user_id'] if token else None
#         return render_template('post.html', post=post_data, current_user_id=current_user_id)
#     else:
#         return redirect(url_for('home'))

# @app.route('/api/posts/<post_id>', methods=['DELETE'])
# @token_required
# def delete_post(post_id):
#     try:
#         post_ref = db.collection('posts').document(post_id)
#         post = post_ref.get()
        
#         if post.exists:
#             post_data = post.to_dict()
#             token = request.cookies.get('token')
#             current_user_id = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])['user_id']
            
#             if post_data.get('has_password'):
#                 password = request.json.get('password')
#                 stored_password = db.collection('post_passwords').document(post_id).get().to_dict()['password']
#                 if password != stored_password:
#                     return jsonify({"success": False, "error": "비밀번호가 일치하지 않습니다."}), 403
#             elif current_user_id != post_data.get('user_id'):
#                 return jsonify({"success": False, "error": "삭제 권한이 없습니다."}), 403
            
#             # 비밀번호가 일치하거나 비밀번호가 없는 경우
#             post_ref.delete()
#             if post_data.get('has_password'):
#                 db.collection('post_passwords').document(post_id).delete()
#             return jsonify({"success": True}), 200
#         else:
#             return jsonify({"success": False, "error": "게시글을 찾을 수 없습니다."}), 404
#     except Exception as e:
#         return jsonify({"success": False, "error": str(e)}), 500

# @app.route('/edit/<post_id>', methods=['GET', 'POST'])
# @token_required
# def edit_post(post_id):
#     post_ref = db.collection('posts').document(post_id)
#     post = post_ref.get()
    
#     if not post.exists:
#         return redirect(url_for('home'))
    
#     post_data = post.to_dict()
#     post_data['id'] = post_id
    
#     if request.method == 'POST':
#         token = request.cookies.get('token')
#         current_user_id = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])['user_id']
        
#         if post_data.get('has_password'):
#             password = request.form.get('password')
#             stored_password = db.collection('post_passwords').document(post_id).get().to_dict()['password']
#             if password != stored_password:
#                 return render_template('edit_post.html', post=post_data, error="비밀번호가 일치하지 않습니다.")
#         elif current_user_id != post_data.get('user_id'):
#             return render_template('edit_post.html', post=post_data, error="수정 권한이 없습니다.")
        
#         # 비밀번호가 일치하거나 비밀번호가 없는 경우
#         post_ref.update({
#             'title': request.form.get('title'),
#             'content': request.form.get('content')
#         })
#         return redirect(url_for('view_post', post_id=post_id))
    
#     return render_template('edit_post.html', post=post_data)

# @app.route('/api/token', methods=['GET'])
# def get_token():
#     token = create_token()
#     response = jsonify({'token': token})
#     response.set_cookie('token', token, httponly=True, secure=True, samesite='Strict')
#     return response

# if __name__ == '__main__':
#     app.run(debug=True)


# ## Ver3
# from flask import Flask, request, render_template, redirect, url_for, jsonify, session
# import firebase_admin
# from firebase_admin import credentials, firestore
# from datetime import datetime
# import os

# app = Flask(__name__)
# app.secret_key = os.urandom(24)  # 세션을 위한 비밀 키 설정

# # Firebase 초기화 코드
# cred = credentials.Certificate('community-test-9a140-firebase-adminsdk-g7m9p-9ad858b701.json')  # 서비스 계정 키 JSON 파일 경로
# firebase_admin.initialize_app(cred)

# # Firestore 클라이언트 초기화
# db = firestore.client()

# @app.route('/', methods=['GET', 'POST'])
# def home():
#     # 서버 사이드 렌더링을 위해 게시글 목록을 가져옵니다.
#     docs = db.collection('posts').order_by('created_at', direction=firestore.Query.DESCENDING).stream()
#     posts = []

#     for doc in docs:
#         post_data = doc.to_dict()
#         created_at = post_data.get('created_at')

#         if isinstance(created_at, datetime):
#             formatted_date = created_at
#         else:
#             # 문자열의 경우 datetime 객체로 변환
#             formatted_date = datetime.fromisoformat(created_at)

#         posts.append({
#             'id': doc.id, 
#             'title': post_data.get('title', '제목 없음'), 
#             'content': post_data.get('content', '내용 없음'),
#             'created_at': formatted_date,
#             'has_password': post_data.get('has_password', False)
#         })

#     return render_template('index.html', posts=posts)

# @app.route('/post/<post_id>')
# def view_post(post_id):
#     post_ref = db.collection('posts').document(post_id)
#     post = post_ref.get()
    
#     if post.exists:
#         post_data = post.to_dict()
#         post_data['id'] = post_id
#         current_temp_user_id = session.get('temp_user_id', '')
#         return render_template('post.html', post=post_data, current_temp_user_id=current_temp_user_id)
#     else:
#         return redirect(url_for('home'))

# @app.route('/delete/<post_id>', methods=['POST'])
# def delete_post(post_id):
#     try:
#         post_ref = db.collection('posts').document(post_id)
#         post = post_ref.get()
        
#         if post.exists:
#             post_data = post.to_dict()
#             if post_data.get('has_password'):
#                 password = request.json.get('password')
#                 stored_password = db.collection('post_passwords').document(post_id).get().to_dict()['password']
#                 if password != stored_password:
#                     return jsonify({"success": False, "error": "비밀번호가 일치하지 않습니다."}), 403
#             elif session.get('temp_user_id') != post_data.get('temp_user_id'):
#                 return jsonify({"success": False, "error": "삭제 권한이 없습니다."}), 403
            
#             # 비밀번호가 일치하거나 비밀번호가 없는 경우
#             post_ref.delete()
#             if post_data.get('has_password'):
#                 db.collection('post_passwords').document(post_id).delete()
#             return jsonify({"success": True}), 200
#         else:
#             return jsonify({"success": False, "error": "게시글을 찾을 수 없습니다."}), 404
#     except Exception as e:
#         return jsonify({"success": False, "error": str(e)}), 500

# @app.route('/edit/<post_id>', methods=['GET', 'POST'])
# def edit_post(post_id):
#     post_ref = db.collection('posts').document(post_id)
#     post = post_ref.get()
    
#     if not post.exists:
#         return redirect(url_for('home'))
    
#     post_data = post.to_dict()
#     post_data['id'] = post_id
    
#     if request.method == 'POST':
#         if post_data.get('has_password'):
#             password = request.form.get('password')
#             stored_password = db.collection('post_passwords').document(post_id).get().to_dict()['password']
#             if password != stored_password:
#                 return render_template('edit_post.html', post=post_data, error="비밀번호가 일치하지 않습니다.")
#         elif session.get('temp_user_id') != post_data.get('temp_user_id'):
#             return render_template('edit_post.html', post=post_data, error="수정 권한이 없습니다.")
        
#         # 비밀번호가 일치하거나 비밀번호가 없는 경우
#         post_ref.update({
#             'title': request.form.get('title'),
#             'content': request.form.get('content')
#         })
#         return redirect(url_for('view_post', post_id=post_id))
    
#     return render_template('edit_post.html', post=post_data)

# if __name__ == '__main__':
#     app.run(debug=True)


# # ## Ver3
# # from flask import Flask, request, render_template, redirect, url_for, jsonify, session
# # import firebase_admin
# # from firebase_admin import credentials, firestore
# # from datetime import datetime
# # import os

# # app = Flask(__name__)
# # app.secret_key = os.urandom(24)  # 세션을 위한 비밀 키 설정

# # # Firebase 초기화 코드
# # cred = credentials.Certificate('community-test-9a140-firebase-adminsdk-g7m9p-9ad858b701.json')  # 서비스 계정 키 JSON 파일 경로
# # firebase_admin.initialize_app(cred)

# # # Firestore 클라이언트 초기화
# # db = firestore.client()

# # @app.route('/', methods=['GET', 'POST'])
# # def home():
# #     if request.method == 'POST':
# #         post_title = request.form.get('title', '')
# #         post_content = request.form.get('content', '')
# #         post_password = request.form.get('password', '')
        
# #         # 세션에 임시 user_id가 없으면 생성
# #         if 'temp_user_id' not in session:
# #             session['temp_user_id'] = os.urandom(16).hex()
        
# #         post = {
# #             'title': post_title,
# #             'content': post_content,
# #             'created_at': datetime.now(),
# #             'has_password': bool(post_password),
# #             'temp_user_id': session['temp_user_id']  # 임시 user_id 사용
# #         }
        
# #         # Firestore에 데이터 추가
# #         doc_ref = db.collection('posts').add(post)
# #         post_id = doc_ref[1].id
        
# #         # 비밀번호가 있는 경우, 별도의 컬렉션에 저장
# #         if post_password:
# #             db.collection('post_passwords').document(post_id).set({'password': post_password})
        
# #         return redirect(url_for('home'))

# #     # Firestore에서 모든 게시글 가져오기
# #     docs = db.collection('posts').order_by('created_at', direction=firestore.Query.DESCENDING).stream()
# #     posts = []

# #     for doc in docs:
# #         post_data = doc.to_dict()
# #         created_at = post_data.get('created_at')

# #         if isinstance(created_at, datetime):
# #             formatted_date = created_at
# #         else:
# #             # 문자열의 경우 datetime 객체로 변환
# #             formatted_date = datetime.fromisoformat(created_at)

# #         posts.append({
# #             'id': doc.id, 
# #             'title': post_data.get('title', '제목 없음'), 
# #             'content': post_data.get('content', '내용 없음'),
# #             'created_at': formatted_date,
# #             'has_password': post_data.get('has_password', False)
# #         })

# #     return render_template('index.html', posts=posts)

# # @app.route('/post/<post_id>')
# # def view_post(post_id):
# #     post_ref = db.collection('posts').document(post_id)
# #     post = post_ref.get()
    
# #     if post.exists:
# #         post_data = post.to_dict()
# #         post_data['id'] = post_id
# #         current_temp_user_id = session.get('temp_user_id', '')
# #         return render_template('post.html', post=post_data, current_temp_user_id=current_temp_user_id)
# #     else:
# #         return redirect(url_for('home'))

# # @app.route('/delete/<post_id>', methods=['POST'])
# # def delete_post(post_id):
# #     try:
# #         post_ref = db.collection('posts').document(post_id)
# #         post = post_ref.get()
        
# #         if post.exists:
# #             post_data = post.to_dict()
# #             if post_data.get('has_password'):
# #                 password = request.json.get('password')
# #                 stored_password = db.collection('post_passwords').document(post_id).get().to_dict()['password']
# #                 if password != stored_password:
# #                     return jsonify({"success": False, "error": "비밀번호가 일치하지 않습니다."}), 403
# #             elif session.get('temp_user_id') != post_data.get('temp_user_id'):
# #                 return jsonify({"success": False, "error": "삭제 권한이 없습니다."}), 403
            
# #             # 비밀번호가 일치하거나 비밀번호가 없는 경우
# #             post_ref.delete()
# #             if post_data.get('has_password'):
# #                 db.collection('post_passwords').document(post_id).delete()
# #             return jsonify({"success": True}), 200
# #         else:
# #             return jsonify({"success": False, "error": "게시글을 찾을 수 없습니다."}), 404
# #     except Exception as e:
# #         return jsonify({"success": False, "error": str(e)}), 500

# # @app.route('/edit/<post_id>', methods=['GET', 'POST'])
# # def edit_post(post_id):
# #     post_ref = db.collection('posts').document(post_id)
# #     post = post_ref.get()
    
# #     if not post.exists:
# #         return redirect(url_for('home'))
    
# #     post_data = post.to_dict()
# #     post_data['id'] = post_id
    
# #     if request.method == 'POST':
# #         if post_data.get('has_password'):
# #             password = request.form.get('password')
# #             stored_password = db.collection('post_passwords').document(post_id).get().to_dict()['password']
# #             if password != stored_password:
# #                 return render_template('edit_post.html', post=post_data, error="비밀번호가 일치하지 않습니다.")
# #         elif session.get('temp_user_id') != post_data.get('temp_user_id'):
# #             return render_template('edit_post.html', post=post_data, error="수정 권한이 없습니다.")
        
# #         # 비밀번호가 일치하거나 비밀번호가 없는 경우
# #         post_ref.update({
# #             'title': request.form.get('title'),
# #             'content': request.form.get('content')
# #         })
# #         return redirect(url_for('view_post', post_id=post_id))
    
# #     return render_template('edit_post.html', post=post_data)

# # if __name__ == '__main__':
# #     app.run(debug=True)