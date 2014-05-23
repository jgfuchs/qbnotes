import os, hashlib

from datetime import date
from functools import wraps
from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash
from flask.ext.sqlalchemy import SQLAlchemy
from flaskext.markdown import Markdown

# general app initialization and configuration

heroku = os.environ.get('HEROKU') == '1'

if heroku:
	db_uri = os.environ['DATABASE_URL']
else:
	db_uri = 'sqlite:///qbtool.db'

app = Flask(__name__)
app.config.update(dict(
	SQLALCHEMY_DATABASE_URI=db_uri,
    SECRET_KEY='43316b82bca7c9847536d08abaae40a0',
    PASSWORD_HASH='11de2afa581597d4846ccf4cc6de36e7bc9789a3e044e29baca35f7f',
    
    version="0.2.2"
))

Markdown(app)
db = SQLAlchemy(app)

class Group(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String)

	def __init__(self, name):
		self.name = name

	def __repr__(self):
		return '<Group %s>' % (self.name)

class Entry(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	title = db.Column(db.String)
	creator = db.Column(db.String)
	notes = db.Column(db.String)

	date_added = db.Column(db.Date)

	group_id = db.Column(db.Integer, db.ForeignKey('group.id'))
	group = db.relationship('Group', backref=db.backref('entries', lazy='dynamic'))

	def __init__(self, title, creator, notes, group):
		self.title = title
		self.creator = creator
		self.notes = notes
		self.group = group
		self.date_added = date.today()

	def __repr__(self):
		return '<Entry \'%s\'>' % self.title

def login_required(f):
	@wraps(f)
	def decorated_function(*args, **kwargs):
		if not session.get('logged_in'):
			return redirect(url_for('login', next=request.url))
		return f(*args, **kwargs)
	return decorated_function

# main app pages

@app.route('/')
@app.route('/index')
@login_required
def all_groups():
	groups = Group.query.all()
	return render_template('all_groups.html', groups=groups)

@app.route('/group/<int:group_id>')
@login_required
def group_detail(group_id):
	group = Group.query.get_or_404(group_id)
	return render_template('group_detail.html', group=group)

@app.route('/entry/<int:entry_id>')
@login_required
def entry_detail(entry_id):
	entry = Entry.query.get_or_404(entry_id)
	return render_template('entry_detail.html', entry=entry)

@app.route('/new_group', methods=['POST'])
def new_group():
	if not session.get('logged_in'):
		abort(401)

	if not request.form['name']:
		abort(400)

	g = Group(request.form['name'])
	db.session.add(g)
	db.session.commit()

	return redirect(url_for('all_groups'))

@app.route('/new_entry', methods=['POST'])
def new_entry():
	if not session.get('logged_in'):
		abort(401)

	if not (request.form['title'] and request.form['creator'] and request.form['notes'] and request.form['group_id']):
		abort(400)

	g = Group.query.get(request.form['group_id'])

	e = Entry(request.form['title'], request.form['creator'], request.form['notes'], g)

	db.session.add(e)
	db.session.commit()

	return redirect(url_for('entry_detail', entry_id=e.id))

@app.route('/edit_entry/<int:entry_id>', methods=['POST'])
def edit_entry(entry_id):
	if not session.get('logged_in'):
		abort(401)

	if not (request.form['title'] and request.form['creator'] and request.form['notes']):
		abort(400)

	e = Entry.query.get(entry_id)
	e.title = request.form['title']
	e.creator = request.form['creator']
	e.notes = request.form['notes']

	db.session.commit()

	return redirect(url_for('entry_detail', entry_id=e.id))

@app.route('/login', methods=['GET', 'POST'])
def login():
	err = None
	if request.method == 'POST':
		if hashlib.sha224(request.form['password']).hexdigest() != app.config['PASSWORD_HASH']:
			err = 'Wrong password!'
		else:
			session['logged_in'] = True
			return redirect(url_for('all_groups'))
	return render_template('login.html', error=err)

@app.route('/logout')
def logout():
	session.pop('logged_in', None)
	return redirect(url_for('login'))

if __name__ == "__main__":
	app.run(host="0.0.0.0", debug=True)
