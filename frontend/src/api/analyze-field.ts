import {
  AnimationResponse,
  CommentaryTrack,
  PlannerDiagnostics,
  createFieldSubmission,
  FieldConfiguration,
} from "../models";

const API_BASE_URL = (
  process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

type BackendErrorBody = {
  detail?: {
    message?: string;
    code?: string;
    issues?: { message?: string }[];
    diagnostics?: PlannerDiagnostics;
  };
};

export class FieldAnalysisError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly diagnostics?: PlannerDiagnostics,
  ) {
    super(message);
    this.name = "FieldAnalysisError";
  }
}

export async function generateCommentary(
  configuration: FieldConfiguration,
  animationResponse: AnimationResponse,
  tacticalInstruction?: string,
  signal?: AbortSignal,
): Promise<CommentaryTrack> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/field-configurations/commentary`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fieldSubmission: createFieldSubmission(configuration, tacticalInstruction),
        // Never send an earlier commentary track back to the model.
        animationResponse: { ...animationResponse, commentary: undefined },
      }),
      signal,
    },
  );
  if (!response.ok) {
    throw new Error("Commentary is currently unavailable.");
  }
  return (await response.json()) as CommentaryTrack;
}

function errorMessage(body: BackendErrorBody, status: number): string {
  const firstIssue = body.detail?.issues?.[0]?.message;
  return (
    body.detail?.message ??
    firstIssue ??
    `The backend could not analyze this field (${status}).`
  );
}

export async function analyzeFieldConfiguration(
  configuration: FieldConfiguration,
  tacticalInstruction?: string,
  signal?: AbortSignal,
): Promise<AnimationResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/field-configurations/analyze`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        createFieldSubmission(configuration, tacticalInstruction),
      ),
      signal,
    },
  );

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as BackendErrorBody;
    throw new FieldAnalysisError(
      errorMessage(body, response.status),
      response.status,
      body.detail?.diagnostics,
    );
  }

  return (await response.json()) as AnimationResponse;
}
