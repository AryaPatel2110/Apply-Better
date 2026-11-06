import React from 'react';

export default function ApplicationResume({applicationId}){
 const url=`/api/applications/${applicationId}/resume`;
 return <div className="application-resume"><p>Resume locked after submission.</p><iframe title="Resume preview" src={url}/><a className="text-link" href={url} target="_blank" rel="noreferrer">Open PDF in a new tab</a></div>;
}
