## Ver3
from flask import Flask, request, render_template, redirect, url_for, jsonify, session
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)  # 세션을 위한 비밀 키 설정

# Firebase 초기화 코드
cred = credentials.Certificate('community-test-9a140-firebase-adminsdk-g7m9p-9ad858b701.json')  # 서비스 계정 키 JSON 파일 경로
firebase_admin.initialize_app(cred)

# Firestore 클라이언트 초기화
db = firestore.client()

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        post_title = request.form.get('title', '')
        post_content = request.form.get('content', '')
        post_password = request.form.get('password', '')
        
        # 세션에 임시 user_id가 없으면 생성
        if 'temp_user_id' not in session:
            session['temp_user_id'] = os.urandom(16).hex()
        
        post = {
            'title': post_title,
            'content': post_content,
            'created_at': datetime.now(),
            'has_password': bool(post_password),
            'temp_user_id': session['temp_user_id']  # 임시 user_id 사용
        }
        
        # Firestore에 데이터 추가
        doc_ref = db.collection('posts').add(post)
        post_id = doc_ref[1].id
        
        # 비밀번호가 있는 경우, 별도의 컬렉션에 저장
        if post_password:
            db.collection('post_passwords').document(post_id).set({'password': post_password})
        
        return redirect(url_for('home'))

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

@app.route('/post/<post_id>')
def view_post(post_id):
    post_ref = db.collection('posts').document(post_id)
    post = post_ref.get()
    
    if post.exists:
        post_data = post.to_dict()
        post_data['id'] = post_id
        current_temp_user_id = session.get('temp_user_id', '')
        return render_template('post.html', post=post_data, current_temp_user_id=current_temp_user_id)
    else:
        return redirect(url_for('home'))

@app.route('/delete/<post_id>', methods=['POST'])
def delete_post(post_id):
    try:
        post_ref = db.collection('posts').document(post_id)
        post = post_ref.get()
        
        if post.exists:
            post_data = post.to_dict()
            if post_data.get('has_password'):
                password = request.json.get('password')
                stored_password = db.collection('post_passwords').document(post_id).get().to_dict()['password']
                if password != stored_password:
                    return jsonify({"success": False, "error": "비밀번호가 일치하지 않습니다."}), 403
            elif session.get('temp_user_id') != post_data.get('temp_user_id'):
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
def edit_post(post_id):
    post_ref = db.collection('posts').document(post_id)
    post = post_ref.get()
    
    if not post.exists:
        return redirect(url_for('home'))
    
    post_data = post.to_dict()
    post_data['id'] = post_id
    
    if request.method == 'POST':
        if post_data.get('has_password'):
            password = request.form.get('password')
            stored_password = db.collection('post_passwords').document(post_id).get().to_dict()['password']
            if password != stored_password:
                return render_template('edit_post.html', post=post_data, error="비밀번호가 일치하지 않습니다.")
        elif session.get('temp_user_id') != post_data.get('temp_user_id'):
            return render_template('edit_post.html', post=post_data, error="수정 권한이 없습니다.")
        
        # 비밀번호가 일치하거나 비밀번호가 없는 경우
        post_ref.update({
            'title': request.form.get('title'),
            'content': request.form.get('content')
        })
        return redirect(url_for('view_post', post_id=post_id))
    
    return render_template('edit_post.html', post=post_data)

if __name__ == '__main__':
    app.run(debug=True)