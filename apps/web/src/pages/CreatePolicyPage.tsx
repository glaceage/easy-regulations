import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";

export function CreatePolicyPage() {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [department, setDepartment] = useState("");
  const [category, setCategory] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const policy = await api.createPolicy({
        code: code.trim(),
        title: title.trim(),
        owner_department: department.trim(),
        category: category.trim() || undefined,
      });
      navigate(`/policies/${policy.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <p>
        <Link to="/policies">← 返回制度库</Link>
      </p>
      <h1 className="page-title">新建制度</h1>
      {error && <div className="error-banner">{error}</div>}
      <div className="card" style={{ maxWidth: 560 }}>
        <form onSubmit={(e) => void handleSubmit(e)}>
          <div className="form-group">
            <label htmlFor="code">制度编码</label>
            <input id="code" value={code} onChange={(e) => setCode(e.target.value)} required />
          </div>
          <div className="form-group">
            <label htmlFor="title">制度名称</label>
            <input id="title" value={title} onChange={(e) => setTitle(e.target.value)} required />
          </div>
          <div className="form-group">
            <label htmlFor="department">归口部门</label>
            <input
              id="department"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="category">分类（可选）</label>
            <input id="category" value={category} onChange={(e) => setCategory(e.target.value)} />
          </div>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "创建中…" : "创建制度"}
          </button>
        </form>
      </div>
    </>
  );
}
